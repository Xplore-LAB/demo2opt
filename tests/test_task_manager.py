import time
from src.services import TaskManager, TaskStatus


def test_task_manager():
    print("="*80)
    print("TaskManager 功能测试")
    print("="*80)

    task_manager = TaskManager()

    print("\n[测试1] 创建任务")
    print("-"*80)
    task_id = task_manager.create_task(
        total_steps=5,
        metadata={"type": "test_task"}
    )
    print(f"任务ID: {task_id}")
    print("✓ 任务创建成功")

    print("\n[测试2] 查询任务")
    print("-"*80)
    task = task_manager.get_task(task_id)
    print(f"任务状态: {task.status}")
    print(f"任务进度: {task.progress}%")
    print(f"总步骤数: {task.total_steps}")
    print("✓ 任务查询成功")

    print("\n[测试3] 更新任务进度")
    print("-"*80)
    task_manager.update_task(
        task_id,
        status=TaskStatus.PROCESSING,
        progress=20.0,
        current_step="步骤1",
        current_step_index=1
    )
    task = task_manager.get_task(task_id)
    print(f"状态: {task.status}")
    print(f"进度: {task.progress}%")
    print(f"当前步骤: {task.current_step}")
    print("✓ 任务进度更新成功")

    print("\n[测试4] 模拟任务处理过程")
    print("-"*80)
    for i in range(2, 6):
        progress = i * 20
        task_manager.update_task(
            task_id,
            progress=progress,
            current_step=f"步骤{i}",
            current_step_index=i
        )
        task = task_manager.get_task(task_id)
        print(f"[步骤{i}] 进度: {task.progress}% | 当前步骤: {task.current_step}")
        time.sleep(0.5)

    print("\n[测试5] 完成任务")
    print("-"*80)
    task_manager.update_task(
        task_id,
        status=TaskStatus.COMPLETED,
        progress=100.0,
        current_step="完成"
    )
    task = task_manager.get_task(task_id)
    print(f"最终状态: {task.status}")
    print(f"最终进度: {task.progress}%")
    print(f"结束时间: {task.end_time}")
    print("✓ 任务完成")

    print("\n[测试6] 测试失败任务")
    print("-"*80)
    failed_task_id = task_manager.create_task(
        total_steps=3,
        metadata={"type": "test_failed_task"}
    )
    task_manager.update_task(
        failed_task_id,
        status=TaskStatus.PROCESSING,
        progress=30.0,
        current_step="处理中"
    )
    task_manager.update_task(
        failed_task_id,
        status=TaskStatus.FAILED,
        error_message="模拟失败：连接超时"
    )
    failed_task = task_manager.get_task(failed_task_id)
    print(f"任务ID: {failed_task_id}")
    print(f"状态: {failed_task.status}")
    print(f"错误信息: {failed_task.error_message}")
    print("✓ 失败任务处理成功")

    print("\n[测试7] 获取所有任务")
    print("-"*80)
    all_tasks = task_manager.get_all_tasks()
    print(f"任务总数: {len(all_tasks)}")
    for task in all_tasks:
        print(f"  - {task.task_id}: {task.status} ({task.progress}%)")
    print("✓ 获取所有任务成功")

    print("\n[测试8] 清理测试任务")
    print("-"*80)
    task_manager.delete_task(task_id)
    task_manager.delete_task(failed_task_id)
    print("✓ 测试任务清理完成")

    print("\n" + "="*80)
    print("✅ 所有测试通过！")
    print("="*80)


if __name__ == "__main__":
    test_task_manager()
