/** @odoo-module **/

// Animation de confettis déclenchée chaque fois que l'effet « rainbow man »
// natif d'Odoo apparaît (notamment lorsqu'une opportunité passe en « Gagné »).

function launchConfetti() {
    const canvas = document.createElement("canvas");
    canvas.style.cssText =
        "position:fixed;inset:0;width:100%;height:100%;pointer-events:none;z-index:100000;";
    document.body.appendChild(canvas);

    const ctx = canvas.getContext("2d");
    const W = (canvas.width = window.innerWidth);
    const H = (canvas.height = window.innerHeight);
    const colors = [
        "#FF9E80", "#FFE57F", "#80D8FF", "#B388FF",
        "#CCFF90", "#FF8A80", "#82B1FF", "#FFD180",
    ];
    const COUNT = 180;
    const parts = [];
    for (let i = 0; i < COUNT; i++) {
        parts.push({
            x: Math.random() * W,
            y: -20 - Math.random() * H * 0.4,
            r: 4 + Math.random() * 7,
            c: colors[(Math.random() * colors.length) | 0],
            vx: -3 + Math.random() * 6,
            vy: 2 + Math.random() * 5,
            rot: Math.random() * Math.PI,
            vrot: -0.25 + Math.random() * 0.5,
        });
    }

    const start = performance.now();
    const DURATION = 2600;
    function frame(now) {
        const elapsed = now - start;
        ctx.clearRect(0, 0, W, H);
        for (const p of parts) {
            p.x += p.vx;
            p.y += p.vy;
            p.vy += 0.06;
            p.rot += p.vrot;
            ctx.save();
            ctx.translate(p.x, p.y);
            ctx.rotate(p.rot);
            ctx.globalAlpha = Math.max(0, 1 - elapsed / DURATION);
            ctx.fillStyle = p.c;
            ctx.fillRect(-p.r / 2, -p.r / 2, p.r, p.r * 0.6);
            ctx.restore();
        }
        if (elapsed < DURATION) {
            requestAnimationFrame(frame);
        } else {
            canvas.remove();
        }
    }
    requestAnimationFrame(frame);
}

let lastFire = 0;
function isReward(node) {
    return (
        node.nodeType === 1 &&
        (node.classList?.contains("o_reward") || !!node.querySelector?.(".o_reward"))
    );
}

function setup() {
    const observer = new MutationObserver((mutations) => {
        for (const m of mutations) {
            for (const node of m.addedNodes) {
                if (isReward(node)) {
                    const now = Date.now();
                    if (now - lastFire > 800) {
                        lastFire = now;
                        launchConfetti();
                    }
                    return;
                }
            }
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
}

if (document.body) {
    setup();
} else {
    document.addEventListener("DOMContentLoaded", setup);
}
