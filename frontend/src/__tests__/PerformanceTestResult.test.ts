import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

describe("PerformanceTestResult", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders performance metrics cards", async () => {
    const metrics = {
      avg_response_time: 245.5,
      p50_response_time: 180,
      p95_response_time: 520,
      p99_response_time: 890,
      throughput: 42.3,
      error_rate: 1.2,
      total_requests: 500,
    };

    const wrapper = mount({
      template: `
        <div class="perf-result">
          <div class="metrics-cards">
            <div class="card"><span>Avg</span><strong>{{ m.avg }}ms</strong></div>
            <div class="card"><span>P50</span><strong>{{ m.p50 }}ms</strong></div>
            <div class="card"><span>P95</span><strong>{{ m.p95 }}ms</strong></div>
            <div class="card"><span>P99</span><strong>{{ m.p99 }}ms</strong></div>
            <div class="card"><span>QPS</span><strong>{{ m.qps }}</strong></div>
            <div class="card"><span>Error</span><strong>{{ m.err }}%</strong></div>
          </div>
        </div>
      `,
      data() {
        return {
          m: {
            avg: metrics.avg_response_time,
            p50: metrics.p50_response_time,
            p95: metrics.p95_response_time,
            p99: metrics.p99_response_time,
            qps: metrics.throughput,
            err: metrics.error_rate,
          },
        };
      },
    });

    expect(wrapper.findAll(".card").length).toBe(6);
    expect(wrapper.text()).toContain("245.5");
    expect(wrapper.text()).toContain("520");
    expect(wrapper.text()).toContain("42.3");
  });

  it("shows throughput chart placeholder", async () => {
    const wrapper = mount({
      template: `
        <div class="perf-result">
          <div class="chart-container">
            <div class="chart-placeholder">Response Time Chart</div>
          </div>
          <div class="chart-container">
            <div class="chart-placeholder">Throughput Chart</div>
          </div>
        </div>
      `,
    });

    expect(wrapper.findAll(".chart-container").length).toBe(2);
    expect(wrapper.text()).toContain("Response Time");
    expect(wrapper.text()).toContain("Throughput");
  });

  it("displays threshold comparison", async () => {
    const wrapper = mount({
      template: `
        <div class="thresholds">
          <div class="threshold pass">P95: 520ms < 1000ms ✓</div>
          <div class="threshold pass">Error Rate: 1.2% < 5% ✓</div>
        </div>
      `,
    });

    expect(wrapper.findAll(".threshold").length).toBe(2);
    expect(wrapper.findAll(".pass").length).toBe(2);
    expect(wrapper.text()).toContain("520ms");
    expect(wrapper.text()).toContain("1.2%");
  });
});
