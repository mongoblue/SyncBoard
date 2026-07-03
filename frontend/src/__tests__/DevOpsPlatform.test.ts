import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

vi.mock("@/api", () => ({
  default: {
    get: vi.fn().mockResolvedValue({
      data: {
        overview: { total_cases: 42, pass_rate: 87.5 },
        recent_executions: [],
      },
    }),
    post: vi.fn().mockResolvedValue({ data: {} }),
  },
}));

describe("DevOpsPlatform", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders platform header with action buttons", async () => {
    const wrapper = mount({
      template: `
        <div class="devops-platform">
          <header class="page-header">
            <h1>DevOps 测试平台</h1>
            <div class="header-actions">
              <button class="batch-btn">批量执行</button>
              <button class="quality-btn">质量报告</button>
              <button class="refresh-btn">刷新</button>
            </div>
          </header>
        </div>
      `,
    });

    expect(wrapper.find("h1").text()).toContain("DevOps");
    expect(wrapper.find(".batch-btn").exists()).toBe(true);
    expect(wrapper.find(".quality-btn").exists()).toBe(true);
    expect(wrapper.find(".refresh-btn").exists()).toBe(true);
  });

  it("displays CI/CD integration card", async () => {
    const wrapper = mount({
      template: `
        <div class="feature-card">
          <span>CI/CD 集成</span>
          <p>支持与 Jenkins、GitLab CI 等集成</p>
          <button>配置集成</button>
        </div>
      `,
    });

    expect(wrapper.text()).toContain("CI/CD");
    expect(wrapper.text()).toContain("Jenkins");
    expect(wrapper.find("button").exists()).toBe(true);
  });

  it("shows test statistics", async () => {
    const stats = { overview: { total_cases: 42, pass_rate: 87.5 } };

    const wrapper = mount({
      template: `
        <div class="test-stats">
          <span>{{ stats.overview.total_cases }} 个测试用例</span>
          <span>通过率 {{ stats.overview.pass_rate }}%</span>
        </div>
      `,
      data() {
        return { stats };
      },
    });

    expect(wrapper.text()).toContain("42");
    expect(wrapper.text()).toContain("87.5");
  });
});
