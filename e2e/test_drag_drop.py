import re
import os
import time
from playwright.sync_api import Page, expect

from e2e.helpers import BASE_URL, login, open_project_card


def test_drag_task_to_done(page: Page):
    print("1. 登录并进入看板...")
    login(page)
    open_project_card(page)

    print("2. 创建拖拽测试任务...")
    task_title = f"DragMe任务_{int(time.time())}"

    todo_column = page.locator(".board-column").first
    expect(todo_column).to_be_visible(timeout=10000)

    add_btn = todo_column.locator('button[title="新增任务"]').first
    expect(add_btn).to_be_visible(timeout=10000)
    add_btn.click()

    dialog = page.locator(".el-dialog").filter(has_text="新建任务").first
    expect(dialog).to_be_visible(timeout=10000)

    dialog.locator("input[placeholder='输入任务标题']").fill(task_title)
    dialog.get_by_role("button", name="创建任务").click()

    task_card = todo_column.get_by_text(task_title, exact=True).first
    expect(task_card).to_be_visible(timeout=10000)

    print("3. 执行拖拽...")
    done_column = page.locator(".board-column").last
    expect(done_column).to_be_visible(timeout=10000)

    try:
        task_card.drag_to(done_column, force=True)
    except Exception:
        src_box = task_card.bounding_box()
        dst_box = done_column.bounding_box()
        if src_box and dst_box:
            page.mouse.move(src_box["x"] + src_box["width"] / 2, src_box["y"] + src_box["height"] / 2)
            page.mouse.down()
            page.wait_for_timeout(200)
            page.mouse.move(dst_box["x"] + dst_box["width"] / 2, dst_box["y"] + dst_box["height"] / 2, steps=30)
            page.wait_for_timeout(200)
            page.mouse.up()

    page.wait_for_timeout(1500)

    print("4. 验证拖拽结果...")
    done_task = done_column.get_by_text(task_title, exact=True)
    expect(done_task).to_be_visible(timeout=10000)

    print("✅ 拖拽测试通过")
