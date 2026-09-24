/** @odoo-module **/

const COLORS = ["#6366f1", "#818cf8", "#22d3ee", "#a855f7", "#818cf8", "#c4b5fd"];

/**
 * Confettis légers dans le modal d'onboarding (célébration badge).
 * @param {HTMLElement} container
 */
export function launchPeConfetti(container) {
    const host = container.closest(".modal-content") || container;
    const layer = document.createElement("div");
    layer.className = "pe-confetti-layer";
    host.style.position = "relative";
    host.appendChild(layer);

    const count = 72;
    for (let i = 0; i < count; i++) {
        const piece = document.createElement("span");
        piece.className = "pe-confetti-piece";
        piece.style.backgroundColor = COLORS[i % COLORS.length];
        piece.style.left = `${Math.random() * 100}%`;
        piece.style.animationDelay = `${Math.random() * 0.4}s`;
        piece.style.animationDuration = `${1.8 + Math.random() * 1.2}s`;
        if (Math.random() > 0.5) {
            piece.style.borderRadius = "50%";
        }
        layer.appendChild(piece);
    }

    window.setTimeout(() => layer.remove(), 3500);
}
