/* guac-main.js
 * Core Guacamole session logic + toolbar helpers.
 * Requires: jQuery, guacamole-1.4.0-all.min.js
 *
 * FIXES:
 *  - Timer starts ONLY when Guacamole connection is established (machine ON)
 *  - Timer STOPS when session disconnects
 *  - Remote canvas is centered inside #container
 *  - GuacMe element selector fixed (was passing "html" string incorrectly)
 */

function GuacMe(element, guest_ip, vncport, session_id, recording_name) {
    "use strict";

    var terminal_connected = false;
    var terminal_client;
    var terminal_element;

    var init = function() {
        /* Build websocket url based on protocol */
        var terminal_ws_url = location.origin.replace(/^http(s?):/, function(match, p1) {
            return (p1 ? 'wss:' : 'ws:');
        });

        /* Initialize Guacamole Client */
        terminal_client = new Guacamole.Client(
            new Guacamole.WebSocketTunnel(terminal_ws_url + '/guac/websocket-tunnel/' + session_id)
        );
        terminal_connect(guest_ip, vncport, recording_name);

        terminal_element = terminal_client.getDisplay().getElement();

        /* Expose client globally so toolbar helpers can use it */
        window._guacClient = terminal_client;

        /* Show the terminal */
        $('#terminal').append(terminal_element);

        /* Disconnect on tab close */
        window.onunload = function() {
            terminal_client.disconnect();
        };

        /* ---- Connection state callback ---- */
        terminal_client.onstatechange = function(state) {
            if (state === 3) {
                /* Machine is ON — start the timer */
                guacStartTimer();

                var dot   = document.getElementById('connDot');
                var label = document.getElementById('connLabel');
                if (dot)   { dot.classList.remove('disconnected'); }
                if (label) { label.textContent = 'Connected'; }
            }

            if (state === 5) {
                /* Machine is OFF — stop the timer */
                guacStopTimer();

                var dot   = document.getElementById('connDot');
                var label = document.getElementById('connLabel');
                if (dot)   { dot.classList.add('disconnected'); }
                if (label) { label.textContent = 'Disconnected'; }
            }
        };

        /* Mouse handling */
        var mouse = new Guacamole.Mouse(terminal_element);

        mouse.onmousedown =
        mouse.onmouseup   =
        mouse.onmousemove = function(mouseState) {
            terminal_client.sendMouseState(mouseState);
        };

        /* Keyboard handling */
        var keyboard = new Guacamole.Keyboard(terminal_element);
        var ctrl, shift = false;

        keyboard.onkeydown = function (keysym) {
            var cancel_event = true;

            if (keysym == 0xFFE1 /* shift */
                || keysym == 0xFFE3 /* ctrl */
                || keysym == 0xFF63 /* insert */
                || keysym == 0x0056 /* V */
                || keysym == 0x0076 /* v */
            ) {
                cancel_event = false;
            }

            if (keysym == 0xFFE1) {
                shift = true;
            } else if (keysym == 0xFFE3) {
                ctrl = true;
            }

            if ((ctrl && shift && keysym == 0x0056)
                || (ctrl && keysym == 0x0076)
                || (shift && keysym == 0xFF63)
            ) {
                window.setTimeout(function() {
                    terminal_client.sendKeyEvent(1, keysym);
                }, 50);
            } else {
                terminal_client.sendKeyEvent(1, keysym);
            }

            return !cancel_event;
        };

        keyboard.onkeyup = function (keysym) {
            if (keysym == 0xFFE1) {
                shift = false;
            } else if (keysym == 0xFFE3) {
                ctrl = false;
            }

            if ((ctrl && shift && keysym == 0x0056)
                || (ctrl && keysym == 0x0076)
                || (shift && keysym == 0xFF63)
            ) {
                window.setTimeout(function() {
                    terminal_client.sendKeyEvent(0, keysym);
                }, 50);
            } else {
                terminal_client.sendKeyEvent(0, keysym);
            }
        };

        $(terminal_element)
            .attr('tabindex', 1)
            .hover(
                function() {
                    var x = window.scrollX, y = window.scrollY;
                    $(this).focus();
                    window.scrollTo(x, y);
                }, function() {
                    $(this).blur();
                }
            )
            .blur(function() {
                keyboard.reset();
            });

        /* Handle paste events */
        $(document).on('paste', function(e) {
            var text = e.originalEvent.clipboardData.getData('text/plain');
            if ($(terminal_element).is(":focus")) {
                terminal_client.setClipboard(text);
            }
        });

        /* Error handling */
        terminal_client.onerror = function(guac_error) {
            terminal_client.disconnect();
            window._guacClient = null;

            /* Stop timer on error */
            guacStopTimer();

            /* Update connection status dot */
            var dot   = document.getElementById('connDot');
            var label = document.getElementById('connLabel');
            if (dot)   dot.classList.add('disconnected');
            if (label) label.textContent = 'Disconnected';

            var dialog = $('#launch_error');
            var dialog_message =
                "Could not connect to guest vm. " +
                "The client detected an unexpected error. " +
                "The server's error message was:";
            var error_message = guac_error.message;

            if (guac_error.message.toLowerCase().startsWith('aborted')) {
                dialog_message = "The remote session has been disconnected.";
                error_message  = "";
            }

            dialog.find('.message').html(dialog_message);
            dialog.find('.error_msg').html(error_message);
            dialog.css('display', 'block');
        };
    };

    var terminal_connect = function(guest_ip, vncport, recording_name) {
        if (terminal_connected) {
            terminal_client.disconnect();
            terminal_connected = false;
        }

        try {
            terminal_client.connect($.param({
                'guest_ip': guest_ip,
                'vncport': vncport,
                'recording_name': recording_name,
            }));
            terminal_connected = true;
        } catch (e) {
            console.warn(e);
            terminal_connected = false;
            throw e;
        }
    };

    init();
}

function stopTask(taskId) {
    var apiUrl = location.origin + "/apiv2/tasks/status/" + taskId + "/";

    fetch(apiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'finish' }),
    })
    .then(function(r) { return r.json(); })
    .then(function(data) { console.log('Response:', data); })
    .catch(function(err) { console.error('Error:', err); });
}

/* ============================================================
   TOOLBAR HELPERS — called from the template's inline <script>
   ============================================================ */

/* --- Toast ------------------------------------------------- */
function guacToast(msg, type) {
    type = type || 'info';
    var container = document.getElementById('toast-container');
    if (!container) return;
    var el = document.createElement('div');
    el.className = 'toast ' + type;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(function() {
        el.classList.add('fade-out');
        setTimeout(function() { el.remove(); }, 250);
    }, 2800);
}

/* --- Session timer ----------------------------------------- */
var _guacTimerInterval = null;

function guacStartTimer() {
    /* Prevent double-start */
    if (_guacTimerInterval) return;

    /* If there is no start time saved (first connection), save it now.*/
    if (!sessionStorage.getItem('guac_timer_start')) {
        sessionStorage.setItem('guac_timer_start', String(Date.now()));
    }

    /* Immediately update the display once before the interval (so it doesn't go blank for 1 second) */
    _guacTimerTick();

    _guacTimerInterval = setInterval(_guacTimerTick, 1000);
}

function _guacTimerTick() {
    var start = parseInt(sessionStorage.getItem('guac_timer_start'), 10) || Date.now();
    var s  = Math.floor((Date.now() - start) / 1000);
    var h  = String(Math.floor(s / 3600)).padStart(2, '0');
    var m  = String(Math.floor((s % 3600) / 60)).padStart(2, '0');
    var sc = String(s % 60).padStart(2, '0');
    var el = document.getElementById('sessionTimer');
    if (el) {
        el.textContent = h + ':' + m + ':' + sc;
        el.classList.remove('stopped');
    }
}

function guacStopTimer() {
    if (_guacTimerInterval) {
        clearInterval(_guacTimerInterval);
        _guacTimerInterval = null;
    }
    /* Clear start time so that the next session starts from zero. */
    sessionStorage.removeItem('guac_timer_start');
    var el = document.getElementById('sessionTimer');
    if (el) {
        el.classList.add('stopped'); 
    }
}

/* --- Screenshot -------------------------------------------- */
function guacScreenshot(taskId) {
    var canvas = document.querySelector('#terminal canvas');
    if (!canvas) { guacToast('No active canvas', 'warn'); return; }

    var flash = document.createElement('div');
    flash.className = 'screenshot-flash';
    document.body.appendChild(flash);
    setTimeout(function() { flash.remove(); }, 400);

    try {
        var a  = document.createElement('a');
        var ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
        a.download = 'screenshot-' + taskId + '-' + ts + '.png';
        a.href = canvas.toDataURL('image/png');
        a.click();
        guacToast('Screenshot saved', 'success');

        var btn = document.getElementById('btnScreenshot');
        if (btn) {
            btn.classList.add('flash-success');
            setTimeout(function() { btn.classList.remove('flash-success'); }, 900);
        }
    } catch (e) {
        guacToast('Screenshot failed: ' + e.message, 'error');
    }
}

/* --- Fit screen toggle ------------------------------------- */
var _guacFitActive = false;

function guacToggleFit() {
    var btn       = document.getElementById('btnFitScreen');
    var container = document.getElementById('container');
    var canvas    = document.querySelector('#terminal canvas');

    if (!canvas) { guacToast('No active canvas', 'warn'); return; }

    _guacFitActive = !_guacFitActive;

    if (_guacFitActive) {
        _guacApplyFit(container, canvas);
        if (btn) btn.classList.add('active');
        guacToast('Fit ON — canvas scaled to window', 'info');
    } else {
        _guacRemoveFit(canvas);
        if (btn) btn.classList.remove('active');
        guacToast('Fit OFF — original resolution restored', 'info');
    }
}

function _guacApplyFit(container, canvas) {
    var cw    = container.clientWidth;
    var ch    = container.clientHeight;
    var iw    = canvas.width  || canvas.offsetWidth;
    var ih    = canvas.height || canvas.offsetHeight;
    if (!iw || !ih) return;

    var scale = Math.min(cw / iw, ch / ih, 1);
    canvas.style.transformOrigin = 'center center';
    canvas.style.transform       = 'scale(' + scale + ')';
    canvas.style.position        = 'relative';
    canvas.style.left            = '';
    canvas.style.top             = '';
}

function _guacRemoveFit(canvas) {
    canvas.style.transform       = '';
    canvas.style.transformOrigin = '';
    canvas.style.position        = '';
    canvas.style.left            = '';
    canvas.style.top             = '';
}

window.addEventListener('resize', function() {
    if (_guacFitActive) {
        var container = document.getElementById('container');
        var canvas    = document.querySelector('#terminal canvas');
        if (container && canvas) _guacApplyFit(container, canvas);
    }
});

/* --- Fullscreen -------------------------------------------- */
function guacToggleFullscreen() {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().catch(function() {
            guacToast('Fullscreen not available', 'warn');
        });
    } else {
        document.exitFullscreen();
    }
}

document.addEventListener('fullscreenchange', function() {
    var btn = document.getElementById('btnFullscreen');
    if (btn) btn.classList.toggle('active', !!document.fullscreenElement);
    if (_guacFitActive) {
        setTimeout(function() {
            var container = document.getElementById('container');
            var canvas    = document.querySelector('#terminal canvas');
            if (container && canvas) _guacApplyFit(container, canvas);
        }, 120);
    }
});

/* --- Send clipboard to session ----------------------------- */
function guacPushClipboard() {
    if (!window._guacClient) { guacToast('Session not ready', 'warn'); return; }
    navigator.clipboard.readText()
        .then(function(text) {
            window._guacClient.setClipboard(text);
            guacToast('Clipboard sent to session', 'success');
        })
        .catch(function() {
            guacToast('Clipboard permission denied', 'error');
        });
}

/* --- Ctrl+Alt+Del ------------------------------------------ */
function guacCtrlAltDel() {
    var c = window._guacClient;
    if (!c) { guacToast('Session not ready', 'warn'); return; }
    c.sendKeyEvent(1, 0xFFE3); // ctrl down
    c.sendKeyEvent(1, 0xFFE9); // alt down
    c.sendKeyEvent(1, 0xFFFF); // del down
    c.sendKeyEvent(0, 0xFFFF); // del up
    c.sendKeyEvent(0, 0xFFE9); // alt up
    c.sendKeyEvent(0, 0xFFE3); // ctrl up
    guacToast('Ctrl+Alt+Del sent', 'info');
}

/* --- Shortcut panel ---------------------------------------- */
function guacToggleShortcuts(show) {
    var panel    = document.getElementById('shortcutPanel');
    var backdrop = document.getElementById('backdrop');
    if (!panel) return;
    var isOpen = panel.classList.contains('visible');
    if (show === undefined) show = !isOpen;
    panel.classList.toggle('visible', show);
    backdrop.classList.toggle('visible', show);
}   