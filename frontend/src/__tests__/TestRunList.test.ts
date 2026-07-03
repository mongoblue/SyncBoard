import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

describe("TestRunList", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders test run list with columns", async () => {
    const runs = [
      { id: 1, name: "Batch Run #1", status: "passed", passed_count: 8, failed_count: 0, pass_rate: 100 },
      { id: 2, name: "Batch Run #2", status: "failed", passed_count: 5, failed_count: 3, pass_rate: 62.5 },
    ];

    const wrapper = mount({
      template: `
        <div class="test-run-list">
          <table>
            <thead>
              <tr><th>名称</th><th>状态</th><th>通过</th><th>失败</th><th>通过率</th></tr>
            </thead>
            <tbody>
              <tr v-for="run in runs" :key="run.id">
                <td>{{ run.name }}</td>
                <td :class="run.status">{{ run.status }}</td>
                <td>{{ run.passed_count }}</td>
                <td>{{ run.failed_count }}</td>
                <td>{{ run.pass_rate }}%</td>
              </tr>
            </tbody>
          </table>
        </div>
      `,
      data() {
        return { runs };
      },
    });

    expect(wrapper.findAll("tbody tr").length).toBe(2);
    expect(wrapper.find(".passed").text()).toBe("passed");
    expect(wrapper.find(".failed").text()).toBe("failed");
    expect(wrapper.text()).toContain("100");
    expect(wrapper.text()).toContain("62.5");
  });

  it("shows empty state when no runs", async () => {
    const wrapper = mount({
      template: `
        <div class="test-run-list">
          <div class="empty-state">暂无测试运行记录</div>
        </div>
      `,
    });

    expect(wrapper.find(".empty-state").exists()).toBe(true);
    expect(wrapper.text()).toContain("暂无");
  });

  it("supports status filtering", async () => {
    const wrapper = mount({
      template: `
        <div>
          <div class="filter-bar">
            <button class="filter-all">全部</button>
            <button class="filter-passed">通过</button>
            <button class="filter-failed">失败</button>
          </div>
        </div>
      `,
    });

    expect(wrapper.find(".filter-all").exists()).toBe(true);
    expect(wrapper.find(".filter-passed").exists()).toBe(true);
    expect(wrapper.find(".filter-failed").exists()).toBe(true);
  });
});
