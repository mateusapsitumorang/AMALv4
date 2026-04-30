/*
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */

function initExamplePlayer(playback_url) {
    "use strict";

    var terminal_url = location.origin + "/recordings/playback/recfile/" + playback_url;
    var RECORDING_URL = terminal_url;

    var player         = document.getElementById('player');
    var display        = document.getElementById('display');
    var playPause      = document.getElementById('play-pause');
    var cancelSeek     = document.getElementById('cancel-seek');
    var position       = document.getElementById('position');
    var positionSlider = document.getElementById('position-slider');
    var duration       = document.getElementById('duration');

    var tunnel           = new Guacamole.StaticHTTPTunnel(RECORDING_URL);
    var recording        = new Guacamole.SessionRecording(tunnel);
    var recordingDisplay = recording.getDisplay();

    /* ── Blur backdrop ────────────────────────────────────────────────────── */

    var bgCanvas  = null;
    var bgCtx     = null;
    var rafHandle = null;
    var isPlaying = false;

    /**
     * DOM structure setelah init:
     *
     * #display  (flex, center)
     *   ├── canvas.bg-blur-canvas   ← z-index: 1, position: absolute  (BLUR)
     *   └── div (guacamole element) ← z-index: 2, position: relative   (VIDEO)
     *         └── canvas            ← canvas Guacamole
     */
    function setupBlurBackdrop() {
        // Guacamole display element
        var guacDiv = recordingDisplay.getElement();

        // Grab the original canvas from inside the guacamole div
        var mainCanvas = guacDiv.querySelector('canvas');
        if (!mainCanvas) {
            // Canvas belum tentu ada saat ini — coba lagi sebentar
            setTimeout(setupBlurBackdrop, 200);
            return;
        }

        // Create a blur canvas with the same dimensions as the Guacamole canvas
        bgCanvas        = document.createElement('canvas');
        bgCanvas.className = 'bg-blur-canvas';
        bgCanvas.width  = mainCanvas.width  || 1280;
        bgCanvas.height = mainCanvas.height || 720;
        bgCtx = bgCanvas.getContext('2d');

        // Insert as the FIRST child of #display (before gua Div) 
        // → bg Canvas = absolute layer behind 
        // → guacDiv = relative layer in front (flex‑centered)
        display.insertBefore(bgCanvas, guacDiv);

        // Sync dimensions if Guacamole resizes its canvas
        var resizeObserver = new MutationObserver(function () {
            if (!bgCanvas || !mainCanvas) return;
            bgCanvas.width  = mainCanvas.width;
            bgCanvas.height = mainCanvas.height;
        });
        resizeObserver.observe(mainCanvas, {
            attributes: true,
            attributeFilter: ['width', 'height']
        });
    }

    /** Copy frames from Guacamole canvas to blur canvas each animation frame */
    function startBlurSync() {
        if (rafHandle) return;

        function sync() {
            var guacDiv    = recordingDisplay.getElement();
            var mainCanvas = guacDiv ? guacDiv.querySelector('canvas') : null;

            if (bgCtx && mainCanvas && mainCanvas.width > 0) {
                try {
                    bgCtx.drawImage(mainCanvas, 0, 0, bgCanvas.width, bgCanvas.height);
                } catch (e) { /* skip tainted canvas */ }
            }
            rafHandle = requestAnimationFrame(sync);
        }
        rafHandle = requestAnimationFrame(sync);
    }

    function stopBlurSync() {
        if (rafHandle) {
            cancelAnimationFrame(rafHandle);
            rafHandle = null;
        }
    }

    /* ── Helpers ──────────────────────────────────────────────────────────── */

    function zeroPad(num, minLength) {
        var str = num.toString();
        while (str.length < minLength) str = '0' + str;
        return str;
    }

    function formatTime(millis) {
        var totalSeconds = Math.floor(millis / 1000);
        var seconds = totalSeconds % 60;
        var minutes = Math.floor(totalSeconds / 60);
        return zeroPad(minutes, 2) + ':' + zeroPad(seconds, 2);
    }

    /* ── Init ─────────────────────────────────────────────────────────────── */

    // Add Guacamole display element to #display
    display.appendChild(recordingDisplay.getElement());

    // Start downloading recording
    recording.connect();

    // Setup blur backdrop after canvas is in DOM
    setTimeout(setupBlurBackdrop, 300);

    /* ── Callbacks ────────────────────────────────────────────────────────── */

    recording.onplay = function () {
        playPause.textContent = 'Pause';
        isPlaying = true;
        startBlurSync();
    };

    recording.onpause = function () {
        playPause.textContent = 'Play';
        isPlaying = false;
        setTimeout(function () {
            if (!isPlaying) stopBlurSync();
        }, 400);
    };

    display.onclick = playPause.onclick = function () {
        if (!recording.isPlaying())
            recording.play();
        else
            recording.pause();
    };

    cancelSeek.onclick = function (e) {
        recording.play();
        player.className = '';
        e.stopPropagation();
    };

    recordingDisplay.onresize = function (width, height) {
        if (!width || !height) return;

        // Scale to CONTAIN — ambil rasio terkecil antara width & height
        var scaleX = display.offsetWidth  / width;
        var scaleY = display.offsetHeight / height;
        var scale  = Math.min(scaleX, scaleY);

        recordingDisplay.scale(scale);
    };

    recording.onseek = function (millis) {
        position.textContent = formatTime(millis);
        positionSlider.value = millis;
    };

    recording.onprogress = function (millis) {
        duration.textContent = formatTime(millis);
        positionSlider.max   = millis;
    };

    positionSlider.onchange = function () {
        player.className = 'seeking';
        recording.seek(positionSlider.value, function () {
            player.className = '';
        });
    };
}