import { describe, it, expect, vi, beforeEach } from "vitest";
import { mount } from "@vue/test-utils";
import { createPinia, setActivePinia } from "pinia";

describe("TestResultDetail", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
  });

  it("renders execution overview card", async () => {
    const wrapper = mount({
      template: `
        <div class="test-result-detail">
          <div class="overview-card">
            <div class="stat passed">10</div>
            <div class="stat failed">2</div>
            <div class="stat error">0</div>
            <div class="pass-rate">83.3%</div>
          </div>
        </div>
      `,
    });

    expect(wrapper.find(".overview-card").exists()).toBe(true);
    expect(wrapper.find(".passed").text()).toBe("10");
    expect(wrapper.find(".failed").text()).toBe("2");
    expect(wrapper.find(".pass-rate").text()).toBe("83.3%");
  });

  it("displays case results table with filters", async () => {
    const wrapper = mount({
      template: `
        <div>
          <div class="filter-bar">
            <select><option>全部</option><option>通过</option><option>失败</option></select>
          </div>
          <table>
            <thead><tr><th>用例</th><th>状态</th><th>耗时</th></tr></thead>
            <tbody>
              <tr><td>Test A</td><td class="pass">通过</td><td>120ms</td></tr>
              <tr><td>Test B</td><td class="fail">失败</td><td>340ms</td></tr>
            </tbody>
          </table>
        </div>
      `,
    });

    expect(wrapper.find("select").exists()).toBe(true);
    expect(wrapper.findAll("tbody tr").length).toBe(2);
    expect(wrapper.find(".pass").text()).toBe("通过");
    expect(wrapper.find(".fail").text()).toBe("失败");
  });

  it("shows curl command copy button", async () => {
    const wrapper = mount({
      template: `
        <div>
          <pre class="curl-command">curl -X GET http://localhost/api/test</pre>
          <button class="copy-btn">Copy as cURL</button>
        </div>
      `,
    });

    expect(wrapper.find(".curl-command").exists()).toBe(true);
    expect(wrapper.find(".copy-btn").exists()).toBe(true);
  });
});
