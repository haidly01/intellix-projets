/** @odoo-module **/

import { registry } from "@web/core/registry";
import { standardFieldProps } from "@web/views/fields/standard_field_props";
import { Component, onMounted, useRef } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";

const COLORS = {
    humains: "#6366f1",
    repondeurs: "#4a4a6a",
    leads: "#06b6d4",
};

export class DoorwayAgentChart extends Component {
    static template = "doorway_agents_dashboard.AgentChartWidget";
    static props = { ...standardFieldProps };

    setup() {
        this.orm = useService("orm");
        this.canvasRef = useRef("chart");
        onMounted(() => this.loadChart());
    }

    async loadChart() {
        const agentId = this.props.record.resId;
        if (!agentId) {
            return;
        }
        const data = await this.orm.call(
            "doorway.agent.profile",
            "get_calls_per_day",
            [agentId, 30]
        );
        this.renderChart(data || []);
    }

    renderChart(data) {
        const canvas = this.canvasRef.el;
        if (!canvas || !data.length) {
            return;
        }
        const ctx = canvas.getContext("2d");
        const dpr = window.devicePixelRatio || 1;
        const width = canvas.parentElement?.clientWidth || 640;
        const height = 200;
        canvas.width = width * dpr;
        canvas.height = height * dpr;
        canvas.style.width = `${width}px`;
        canvas.style.height = `${height}px`;
        ctx.scale(dpr, dpr);
        ctx.clearRect(0, 0, width, height);

        const pad = { l: 36, r: 12, t: 12, b: 28 };
        const chartW = width - pad.l - pad.r;
        const chartH = height - pad.t - pad.b;
        const maxVal = Math.max(
            1,
            ...data.flatMap((d) => [d.humains, d.repondeurs, d.leads])
        );
        const barW = chartW / data.length;
        const stackKeys = ["humains", "repondeurs", "leads"];

        data.forEach((point, idx) => {
            let yBase = pad.t + chartH;
            const x = pad.l + idx * barW + barW * 0.15;
            const w = barW * 0.7;
            stackKeys.forEach((key) => {
                const val = point[key] || 0;
                const h = (val / maxVal) * chartH;
                yBase -= h;
                ctx.fillStyle = COLORS[key];
                ctx.fillRect(x, yBase, w, h);
            });
            if (idx % Math.ceil(data.length / 10) === 0) {
                ctx.fillStyle = "#6b6b8a";
                ctx.font = "10px sans-serif";
                ctx.textAlign = "center";
                ctx.fillText(point.date, x + w / 2, height - 8);
            }
        });

        ctx.strokeStyle = "rgba(255,255,255,0.08)";
        ctx.beginPath();
        ctx.moveTo(pad.l, pad.t);
        ctx.lineTo(pad.l, pad.t + chartH);
        ctx.stroke();

        const legend = [
            ["Humains", COLORS.humains],
            ["Répondeurs", COLORS.repondeurs],
            ["Leads", COLORS.leads],
        ];
        let lx = pad.l;
        ctx.font = "11px sans-serif";
        legend.forEach(([label, color]) => {
            ctx.fillStyle = color;
            ctx.fillRect(lx, 4, 10, 10);
            ctx.fillStyle = "#a0a0b8";
            ctx.fillText(label, lx + 14, 13);
            lx += ctx.measureText(label).width + 28;
        });
    }
}

registry.category("fields").add("doorway_agent_chart", {
    component: DoorwayAgentChart,
});
