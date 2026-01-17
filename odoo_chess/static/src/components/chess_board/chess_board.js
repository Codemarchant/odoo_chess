/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";
import { ensureJQuery } from "@web/core/ensure_jquery";

/**
 * ChessBoard OWL Component
 * Wraps chessboard.js library in an OWL component for use in Odoo forms.
 */
export class ChessBoard extends Component {
    static template = "odoo_chess.ChessBoard";
    static props = {
        ...standardFieldProps,
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.action = useService("action");
        this.busService = useService("bus_service");

        this.boardRef = useRef("board");
        this.board = null;
        this._resizeHandler = null;

        // Preload sound effects
        this.sounds = {
            move: new Audio("/odoo_chess/static/src/sounds/move.mp3"),
            capture: new Audio("/odoo_chess/static/src/sounds/capture.mp3"),
            castle: new Audio("/odoo_chess/static/src/sounds/castle.mp3"),
            check: new Audio("/odoo_chess/static/src/sounds/check.mp3"),
            notify: new Audio("/odoo_chess/static/src/sounds/notify.mp3"),
            victory: new Audio("/odoo_chess/static/src/sounds/victory.mp3"),
            defeat: new Audio("/odoo_chess/static/src/sounds/defeat.mp3"),
            draw: new Audio("/odoo_chess/static/src/sounds/draw.mp3"),
        };
        // Preload all sounds
        Object.values(this.sounds).forEach(audio => audio.load());

        // Bound handlers for bus subscriptions (needed for cleanup)
        this._boundHandleMove = this._handleMove.bind(this);
        this._boundHandleGameEnd = this._handleGameEnd.bind(this);
        this._boundHandleDrawOffer = this._handleDrawOffer.bind(this);
        this._boundHandleDrawDeclined = this._handleDrawDeclined.bind(this);

        this.state = useState({
            fen: this.props.record.data[this.props.name] || "start",
            isMyTurn: false,
            gameOver: false,
            lastMove: null,
            legalMoves: [],
            isCheck: false,
            drawOffered: false,
            currentFact: "",
            // Promotion dialog state
            showPromotion: false,
            promotionColor: "w",  // 'w' or 'b'
            pendingPromotion: null,  // {source, target, piece, oldFen}
            // Time control state
            isTimed: false,
            whiteTime: 0,  // milliseconds
            blackTime: 0,  // milliseconds
            activeClock: "none",  // 'white', 'black', or 'none'
            lastSyncTime: null,  // when times were last synced from server
            whiteTimeDisplay: "0:00",
            blackTimeDisplay: "0:00",
        });

        // Timer interval reference for clock countdown
        this.clockTimer = null;

        // Flag to prevent multiple timeout claims
        this._claimingTimeout = false;

        // Get game data from record
        this.gameId = this.props.record.resId;
        this.gameData = null;
        this.busChannel = null;

        // Chess.js instance for client-side move validation and sound detection
        this.chess = null;

        // Track pending move to avoid double-animation from bus updates
        this._pendingMoveUci = null;

        onMounted(() => {
            this._initBoard();
            this._loadGameData();
            this._loadRandomFact();
            this._subscribeToBus();
            // Add resize listener
            this._resizeHandler = () => this._handleResize();
            window.addEventListener("resize", this._resizeHandler);
        });

        onWillUnmount(() => {
            this._cleanup();
            this._unsubscribeFromBus();
            if (this._resizeHandler) {
                window.removeEventListener("resize", this._resizeHandler);
            }
            // Clean up clock timer
            this._stopClockTimer();
        });
    }

    async _subscribeToBus() {
        if (!this.gameId) return;

        // Channel format: chess_game_{id} - matches Python _broadcast methods
        this.busChannel = `chess_game_${this.gameId}`;

        // Add channel to bus service
        await this.busService.addChannel(this.busChannel);

        // Subscribe to specific notification types
        this.busService.subscribe("chess_move", this._boundHandleMove);
        this.busService.subscribe("chess_game_end", this._boundHandleGameEnd);
        this.busService.subscribe("chess_draw_offer", this._boundHandleDrawOffer);
        this.busService.subscribe("chess_draw_declined", this._boundHandleDrawDeclined);
    }

    _unsubscribeFromBus() {
        if (this.busChannel) {
            this.busService.deleteChannel(this.busChannel);
        }
        // Unsubscribe from notification types
        this.busService.unsubscribe("chess_move", this._boundHandleMove);
        this.busService.unsubscribe("chess_game_end", this._boundHandleGameEnd);
        this.busService.unsubscribe("chess_draw_offer", this._boundHandleDrawOffer);
        this.busService.unsubscribe("chess_draw_declined", this._boundHandleDrawDeclined);
    }

    async _initBoard() {
        // Ensure jQuery is loaded (required by chessboard.js)
        await ensureJQuery();

        // Wait for chessboard.js to be available
        if (typeof Chessboard === "undefined") {
            console.warn("Chessboard.js not loaded yet, retrying...");
            setTimeout(() => this._initBoard(), 100);
            return;
        }

        // Wait for DOM to be fully ready
        await new Promise(resolve => setTimeout(resolve, 150));

        if (!this.boardRef.el) {
            console.warn("Board element not found, retrying...");
            setTimeout(() => this._initBoard(), 100);
            return;
        }

        // Get the wrapper element to determine available width
        const wrapperEl = this.boardRef.el.closest('.o_chess_board_wrapper');
        let containerWidth = wrapperEl ? wrapperEl.offsetWidth : 800;

        // If width is too small, the DOM isn't ready - retry
        if (containerWidth < 200) {
            console.warn("Container width too small, retrying...", containerWidth);
            setTimeout(() => this._initBoard(), 100);
            return;
        }

        // Cap at 784px (same as chess.com)
        const boardSize = Math.min(containerWidth, 784);
        this.boardRef.el.style.width = boardSize + "px";

        const config = {
            position: this.state.fen,
            draggable: true,
            pieceTheme: "/odoo_chess/static/lib/chessboardjs/img/chesspieces/wikipedia/{piece}.png",
            onDragStart: this._onDragStart.bind(this),
            onDrop: this._onDrop.bind(this),
            moveSpeed: 150,
            snapbackSpeed: 50,
            snapSpeed: 25,
        };

        this.board = Chessboard(this.boardRef.el, config);

        // Set orientation based on player color
        if (this.gameData && this.gameData.my_color === "black") {
            this.board.orientation("black");
        }

        // Sync side panel height after board renders
        setTimeout(() => this._syncSidePanelHeight(), 100);
    }

    async _loadGameData() {
        if (!this.gameId) return;

        try {
            const result = await rpc("/chess/game/" + this.gameId + "/state", {});
            if (result.error) {
                this.notification.add(result.error, { type: "danger" });
                return;
            }

            this.gameData = result;
            this.state.fen = result.fen;
            this.state.isMyTurn = result.is_my_turn;
            this.state.isCheck = result.is_check;
            this.state.drawOffered = !!result.draw_offered_by;
            this.state.gameOver = result.state === "completed";

            // Initialize time control state
            this.state.isTimed = result.is_timed || false;
            if (this.state.isTimed) {
                this._syncTimeFromServer({
                    white_time: result.white_time,
                    black_time: result.black_time,
                    active_clock: result.active_clock,
                });
                this._initClockTimer();
            }

            // Initialize chess.js with current position
            if (typeof Chess !== "undefined") {
                this.chess = new Chess(result.fen);
            }

            // Update board position and orientation
            if (this.board) {
                this.board.position(result.fen);
                if (result.my_color === "black") {
                    this.board.orientation("black");
                }
                // Sync side panel height after board update
                setTimeout(() => this._syncSidePanelHeight(), 100);
            }
        } catch (error) {
            console.error("Failed to load game data:", error);
        }
    }

    _cleanup() {
        if (this.board) {
            this.board.destroy();
            this.board = null;
        }
    }

    _handleResize() {
        if (this.board && this.boardRef.el) {
            const wrapperEl = this.boardRef.el.closest('.o_chess_board_wrapper');
            if (wrapperEl) {
                const boardSize = Math.min(wrapperEl.offsetWidth, 784);
                this.boardRef.el.style.width = boardSize + "px";
            }
            this.board.resize();
            this._syncSidePanelHeight();
        }
    }

    _syncSidePanelHeight() {
        // Sync side panel height with board height (desktop layout)
        if (!this.boardRef.el) return;

        const boardEl = this.boardRef.el;
        const sidePanel = boardEl.closest('.o_chess_game_area')?.querySelector('.o_chess_side_panel');

        if (sidePanel && boardEl.offsetHeight > 0) {
            sidePanel.style.height = boardEl.offsetHeight + "px";
        }
    }

    // Chessboard.js event handlers
    _onDragStart(source, piece, position, orientation) {
        // Don't allow moves if game is over
        if (this.state.gameOver) return false;

        // Only allow moving pieces if it's user's turn
        if (!this.state.isMyTurn) return false;

        // Only allow moving own pieces
        const myColor = this.gameData?.my_color;
        if (myColor === "white" && piece.search(/^b/) !== -1) return false;
        if (myColor === "black" && piece.search(/^w/) !== -1) return false;

        return true;
    }

    _onDrop(source, target, piece, newPos, oldPos, orientation) {
        // If dropped off board, just snapback (no API call needed)
        if (target === "offboard") {
            return "snapback";
        }

        // If dropped on same square, just snapback
        if (source === target) {
            return "snapback";
        }

        // Check for pawn promotion
        const isPawn = piece.toLowerCase().includes("p");
        const isPromotion = isPawn && (target[1] === "8" || target[1] === "1");

        // Store the old FEN for rollback
        const oldFen = this.state.fen;

        if (isPromotion) {
            // Show promotion dialog and wait for user selection
            this.state.showPromotion = true;
            this.state.promotionColor = piece.startsWith("w") ? "w" : "b";
            this.state.pendingPromotion = { source, target, piece, oldFen };
            // Don't make the move yet - wait for promotion piece selection
            return;
        }

        // Normal move (no promotion)
        const uciMove = source + target;

        // Use chess.js to determine move type and play appropriate sound
        this._playMoveSound(source, target, null);

        // Track this move to avoid double-animation from bus
        this._pendingMoveUci = uciMove;

        // Make the move request asynchronously
        this._makeMove(uciMove, oldFen, source, target);

        // Don't return anything - let the piece stay where dropped
        // If move is invalid, _makeMove will reset the board
        // If valid, the piece is already in place (instant feedback)
    }

    async _makeMove(uciMove, oldFen, source, target) {
        // For bot games, freeze clocks while waiting for bot response
        const savedActiveClock = this.state.activeClock;
        if (this.gameData?.is_bot_game && this.state.isTimed) {
            this.state.activeClock = 'none';
        }

        try {
            const result = await rpc("/chess/game/" + this.gameId + "/move", {
                uci_move: uciMove,
            });

            if (result.error) {
                // Clear pending move flag
                this._pendingMoveUci = null;
                // Restore clock state on error (for bot games)
                if (this.gameData?.is_bot_game && this.state.isTimed) {
                    this.state.activeClock = savedActiveClock;
                }
                // Silently reset board position on invalid move (no notification)
                if (this.board) {
                    this.board.position(oldFen, false);
                }
                // Re-sync chess.js to the valid position
                if (this.chess) {
                    this.chess.load(oldFen);
                }
                return;
            }

            // Update state with new FEN
            this.state.fen = result.fen;
            this.state.isMyTurn = result.is_my_turn;
            this.state.lastMove = { from: source, to: target };

            // Sync time from response (for timed games)
            if (this.state.isTimed && result.white_time !== undefined) {
                this._syncTimeFromServer({
                    white_time: result.white_time,
                    black_time: result.black_time,
                    active_clock: result.active_clock,
                });
            }

            // Sync chess.js to server's authoritative FEN
            if (this.chess) {
                this.chess.load(result.fen);
            }

            // Update board position to new FEN (no animation - piece already there)
            if (this.board) {
                this.board.position(result.fen, false);
            }

            // Clear pending move flag
            this._pendingMoveUci = null;

            if (result.game_over) {
                this.state.gameOver = true;
                this._showGameResult(result.result);
            }

            // Load new random fact
            this._loadRandomFact();
        } catch (error) {
            console.error("Move error:", error);
            this._pendingMoveUci = null;
            // Restore clock state on error (for bot games)
            if (this.gameData?.is_bot_game && this.state.isTimed) {
                this.state.activeClock = savedActiveClock;
            }
            this.notification.add(_t("Failed to make move"), { type: "danger" });
            // Ensure board is at old position (no animation)
            if (this.board) {
                this.board.position(oldFen, false);
            }
        }
    }

    // Sound methods
    _playSound(soundName) {
        const sound = this.sounds[soundName];
        if (sound) {
            // Clone to allow overlapping sounds
            const clone = sound.cloneNode();
            clone.play().catch((e) => {
                console.warn("Chess sound play error:", soundName, e);
            });
        }
    }

    _playMoveSound(source, target, promotion = null) {
        // Use chess.js to determine move type and play appropriate sound
        if (!this.chess) {
            this._playSound("move");
            return;
        }

        // Try the move on our local chess instance
        const moveObj = {
            from: source,
            to: target,
        };
        if (promotion) {
            moveObj.promotion = promotion;
        }

        const move = this.chess.move(moveObj);
        if (!move) {
            // Invalid move according to chess.js, just play generic sound
            this._playSound("move");
            return;
        }

        // Determine sound based on move result
        // Priority: checkmate > check > castle > capture > move
        // Note: chess.js uses in_checkmate/in_check (not isCheckmate/isCheck)
        let soundType;
        if (this.chess.in_checkmate()) {
            soundType = "check";
        } else if (this.chess.in_check()) {
            soundType = "check";
        } else if (move.flags.includes("k") || move.flags.includes("q")) {
            soundType = "castle";
        } else if (move.captured) {
            soundType = "capture";
        } else {
            soundType = "move";
        }
        this._playSound(soundType);

        // Note: We don't undo the move - the chess instance stays in sync
        // It will be re-synced when we receive the server response or bus update
    }

    _playSoundForMove(san) {
        // Determine sound based on SAN notation
        // Priority: checkmate > check > castle > capture > move
        let soundType;
        if (san.includes("#")) {
            soundType = "check";
        } else if (san.includes("+")) {
            soundType = "check";
        } else if (san === "O-O" || san === "O-O-O") {
            soundType = "castle";
        } else if (san.includes("x")) {
            soundType = "capture";
        } else {
            soundType = "move";
        }
        this._playSound(soundType);
    }

    _playSoundForGameEnd(result, isWinner) {
        if (result === "draw") {
            this._playSound("draw");
        } else if (isWinner) {
            this._playSound("victory");
        } else {
            this._playSound("defeat");
        }
    }

    // Bus message handlers
    _handleMove(payload) {
        // Filter: only handle messages for this game
        if (payload.game_id !== this.gameId) return;

        // Check if this is our own move that we already handled
        const isOwnMove = this._pendingMoveUci === payload.uci;
        if (isOwnMove) {
            // Clear the flag - we've now received confirmation
            this._pendingMoveUci = null;
            // Skip - we already updated the board position
            return;
        }

        this.state.fen = payload.fen;
        this.state.isCheck = payload.is_check || false;

        // Sync time from move payload (for timed games)
        if (this.state.isTimed && payload.white_time !== undefined) {
            this._syncTimeFromServer({
                white_time: payload.white_time,
                black_time: payload.black_time,
                active_clock: payload.active_clock,
            });
        }

        // Sync chess.js to the new position
        if (this.chess) {
            this.chess.load(payload.fen);
        }

        // Animate opponent/bot moves
        if (this.board) {
            this.board.position(payload.fen, true);
        }

        // Update turn state based on FEN (whose turn it is now)
        const fenParts = payload.fen.split(' ');
        const turnColor = fenParts[1] === 'w' ? 'white' : 'black';
        this.state.isMyTurn = (turnColor === this.gameData?.my_color);

        // Play sound for opponent's moves (own moves already played in _onDrop)
        // For bot games: play sound if it's a bot move
        // For human games: play sound if it's now our turn (opponent just moved)
        const shouldPlaySound = this.gameData?.is_bot_game
            ? payload.is_bot_move
            : this.state.isMyTurn;

        if (shouldPlaySound) {
            if (payload.san) {
                this._playSoundForMove(payload.san);
            } else {
                this._playSound("notify");
            }
        }

        // Visual feedback for the move
        this.state.lastMove = {
            from: payload.uci.substring(0, 2),
            to: payload.uci.substring(2, 4),
        };

        // Load a new random fact when opponent moves
        if (this.state.isMyTurn) {
            this._loadRandomFact();
        }
    }

    _handleGameEnd(payload) {
        // Filter: only handle messages for this game
        if (payload.game_id !== this.gameId) return;

        this.state.gameOver = true;
        this._stopClockTimer();
        this._showGameResult(payload.result);
    }

    _handleDrawOffer(payload) {
        // Filter: only handle messages for this game
        if (payload.game_id !== this.gameId) return;

        this.state.drawOffered = true;
        this.notification.add(
            _t("%s has offered a draw", payload.offered_by_name),
            { type: "info" }
        );
    }

    _handleDrawDeclined(payload) {
        // Filter: only handle messages for this game
        if (payload.game_id !== this.gameId) return;

        this.state.drawOffered = false;
        this.notification.add(_t("Draw offer was declined"), { type: "info" });
    }

    _showGameResult(result) {
        let message;
        switch (result) {
            case "white_wins":
                message = _t("White wins!");
                break;
            case "black_wins":
                message = _t("Black wins!");
                break;
            case "draw":
                message = _t("Game drawn!");
                break;
            default:
                message = _t("Game over!");
        }
        this.notification.add(message, { type: "success" });

        // Play game end sound
        const myColor = this.gameData?.my_color;
        const isWinner = (result === "white_wins" && myColor === "white") ||
                         (result === "black_wins" && myColor === "black");
        this._playSoundForGameEnd(result, isWinner);

        // Reload the form view to update the state (statusbar, etc.)
        setTimeout(async () => {
            await this.props.record.load();
        }, 500);
    }

    async _loadRandomFact() {
        try {
            const result = await rpc("/chess/random_fact", {});
            if (result.fact) {
                this.state.currentFact = result.fact;
            }
        } catch (error) {
            // Silently fail for facts
        }
    }

    // Time control methods
    _initClockTimer() {
        if (this.clockTimer) {
            clearInterval(this.clockTimer);
        }

        // Update display every 100ms for smooth countdown
        this.clockTimer = setInterval(() => {
            this._updateClockDisplay();
        }, 100);
    }

    _updateClockDisplay() {
        if (!this.state.isTimed || this.state.gameOver) {
            return;
        }

        if (this.state.activeClock === "none") {
            return;
        }

        // Calculate elapsed since last sync
        const now = Date.now();
        const elapsed = this.state.lastSyncTime ? now - this.state.lastSyncTime : 0;

        // Calculate display times (deduct from active clock)
        let whiteDisplay = this.state.whiteTime;
        let blackDisplay = this.state.blackTime;

        if (this.state.activeClock === "white") {
            whiteDisplay = Math.max(0, this.state.whiteTime - elapsed);
        } else if (this.state.activeClock === "black") {
            blackDisplay = Math.max(0, this.state.blackTime - elapsed);
        }

        // Update display strings
        this.state.whiteTimeDisplay = this._formatTime(whiteDisplay);
        this.state.blackTimeDisplay = this._formatTime(blackDisplay);

        // Check for timeout - either player's time hitting 0
        // Server determines winner based on whose turn it is
        const activeClockTime = this.state.activeClock === "white" ? whiteDisplay : blackDisplay;

        // If active player's time hits 0, claim timeout (server determines result)
        if (activeClockTime <= 0 && !this._claimingTimeout) {
            this._claimTimeout();
        }
    }

    async _claimTimeout() {
        // Prevent multiple claims
        if (this._claimingTimeout) return;
        this._claimingTimeout = true;

        try {
            const result = await rpc("/chess/game/" + this.gameId + "/claim_timeout", {});
            if (result.success) {
                this.state.gameOver = true;
                this._stopClockTimer();
                this._showGameResult(result.result);
            } else if (result.error) {
                // Server says no timeout - maybe clock sync issue, don't spam
                console.warn("Timeout claim rejected:", result.error);
            }
        } catch (error) {
            console.error("Failed to claim timeout:", error);
        } finally {
            // Allow retry after a delay if it failed
            setTimeout(() => {
                this._claimingTimeout = false;
            }, 2000);
        }
    }

    _stopClockTimer() {
        if (this.clockTimer) {
            clearInterval(this.clockTimer);
            this.clockTimer = null;
        }
    }

    _formatTime(milliseconds) {
        if (milliseconds <= 0) {
            return "0:00";
        }

        const totalSeconds = Math.floor(milliseconds / 1000);
        const hours = Math.floor(totalSeconds / 3600);
        const minutes = Math.floor((totalSeconds % 3600) / 60);
        const seconds = totalSeconds % 60;
        const tenths = Math.floor((milliseconds % 1000) / 100);

        if (hours > 0) {
            return `${hours}:${minutes.toString().padStart(2, "0")}:${seconds.toString().padStart(2, "0")}`;
        } else if (totalSeconds < 20) {
            // Show tenths when under 20 seconds
            return `${minutes}:${seconds.toString().padStart(2, "0")}.${tenths}`;
        } else {
            return `${minutes}:${seconds.toString().padStart(2, "0")}`;
        }
    }

    _syncTimeFromServer(timeData) {
        if (!timeData) return;

        this.state.whiteTime = timeData.white_time || 0;
        this.state.blackTime = timeData.black_time || 0;
        this.state.activeClock = timeData.active_clock || "none";
        this.state.lastSyncTime = Date.now();

        // Update display immediately
        this.state.whiteTimeDisplay = this._formatTime(this.state.whiteTime);
        this.state.blackTimeDisplay = this._formatTime(this.state.blackTime);
    }

    _isLowTime(milliseconds) {
        return milliseconds > 0 && milliseconds < 30000; // Under 30 seconds
    }

    _isCriticalTime(milliseconds) {
        return milliseconds > 0 && milliseconds < 10000; // Under 10 seconds
    }

    // Get current time for a player accounting for running clock
    _getCurrentTime(player) {
        if (!this.state.isTimed) return 0;

        const baseTime = player === "white" ? this.state.whiteTime : this.state.blackTime;

        if (this.state.activeClock === player && this.state.lastSyncTime) {
            const elapsed = Date.now() - this.state.lastSyncTime;
            return Math.max(0, baseTime - elapsed);
        }

        return baseTime;
    }

    // Promotion piece selection handler
    onSelectPromotion(piece) {
        if (!this.state.pendingPromotion) return;

        const { source, target, oldFen } = this.state.pendingPromotion;
        const uciMove = source + target + piece;

        // Hide promotion dialog
        this.state.showPromotion = false;
        this.state.pendingPromotion = null;

        // Play move sound
        this._playMoveSound(source, target, piece);

        // Track this move to avoid double-animation from bus
        this._pendingMoveUci = uciMove;

        // Make the move request
        this._makeMove(uciMove, oldFen, source, target);
    }

    onCancelPromotion() {
        if (!this.state.pendingPromotion) return;

        const { oldFen } = this.state.pendingPromotion;

        // Reset board to previous position
        if (this.board) {
            this.board.position(oldFen, false);
        }

        // Hide promotion dialog
        this.state.showPromotion = false;
        this.state.pendingPromotion = null;
    }

    // Action handlers
    async onResign() {
        if (confirm(_t("Are you sure you want to resign?"))) {
            try {
                await rpc("/chess/game/" + this.gameId + "/resign", {});
            } catch (error) {
                this.notification.add(_t("Failed to resign"), { type: "danger" });
            }
        }
    }

    async onOfferDraw() {
        try {
            await rpc("/chess/game/" + this.gameId + "/offer_draw", {});
            this.notification.add(_t("Draw offer sent"), { type: "info" });
        } catch (error) {
            this.notification.add(_t("Failed to offer draw"), { type: "danger" });
        }
    }

    async onAcceptDraw() {
        try {
            await rpc("/chess/game/" + this.gameId + "/accept_draw", {});
        } catch (error) {
            this.notification.add(_t("Failed to accept draw"), { type: "danger" });
        }
    }

    async onDeclineDraw() {
        try {
            await rpc("/chess/game/" + this.gameId + "/decline_draw", {});
            this.state.drawOffered = false;
        } catch (error) {
            this.notification.add(_t("Failed to decline draw"), { type: "danger" });
        }
    }

    // Getters for template
    get turnIndicator() {
        if (this.state.gameOver) return _t("Game Over");
        return this.state.isMyTurn ? _t("Your turn!") : _t("Opponent's turn");
    }

    get turnIndicatorClass() {
        if (this.state.gameOver) return "text-muted";
        return this.state.isMyTurn ? "text-success fw-bold" : "text-warning";
    }

    // Clock getters for template
    get opponentClockClass() {
        if (!this.state.isTimed) return "";
        const myColor = this.gameData?.my_color;
        const opponentColor = myColor === "white" ? "black" : "white";
        const opponentTime = this._getCurrentTime(opponentColor);
        const isActive = this.state.activeClock === opponentColor;

        let classes = ["o_chess_clock", "o_chess_clock_opponent"];
        if (isActive) classes.push("o_clock_active");
        if (this._isCriticalTime(opponentTime)) {
            classes.push("o_clock_critical");
        } else if (this._isLowTime(opponentTime)) {
            classes.push("o_clock_low");
        }
        return classes.join(" ");
    }

    get myClockClass() {
        if (!this.state.isTimed) return "";
        const myColor = this.gameData?.my_color || "white";
        const myTime = this._getCurrentTime(myColor);
        const isActive = this.state.activeClock === myColor;

        let classes = ["o_chess_clock", "o_chess_clock_mine"];
        if (isActive) classes.push("o_clock_active");
        if (this._isCriticalTime(myTime)) {
            classes.push("o_clock_critical");
        } else if (this._isLowTime(myTime)) {
            classes.push("o_clock_low");
        }
        return classes.join(" ");
    }

    get opponentTimeDisplay() {
        const myColor = this.gameData?.my_color;
        return myColor === "white" ? this.state.blackTimeDisplay : this.state.whiteTimeDisplay;
    }

    get myTimeDisplay() {
        const myColor = this.gameData?.my_color;
        return myColor === "white" ? this.state.whiteTimeDisplay : this.state.blackTimeDisplay;
    }

    get opponentName() {
        // For bot games, show the bot's name
        if (this.gameData?.is_bot_game && this.gameData?.bot_name) {
            return this.gameData.bot_name;
        }
        const myColor = this.gameData?.my_color;
        if (myColor === "white") {
            return this.gameData?.black_player?.name || "Black";
        }
        return this.gameData?.white_player?.name || "White";
    }

    get myName() {
        const myColor = this.gameData?.my_color;
        if (myColor === "white") {
            return this.gameData?.white_player?.name || "White";
        }
        return this.gameData?.black_player?.name || "Black";
    }
}

// Register as a field widget
export const chessBoardField = {
    component: ChessBoard,
    supportedTypes: ["char"],
};

registry.category("fields").add("chess_board", chessBoardField);
