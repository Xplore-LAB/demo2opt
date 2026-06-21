import os
import time
import requests
import json
from typing import Optional

import pytest


pytestmark = pytest.mark.skipif(
    os.getenv("RUN_PROGRESS_API_TESTS") != "1",
    reason="Integration API test. Set RUN_PROGRESS_API_TESTS=1 to enable.",
)


class ProgressQueryClient:
    def __init__(self, base_url: str = "http://localhost:5000"):
        self.base_url = base_url.rstrip('/')

    def health_check(self) -> dict:
        response = requests.get(f"{self.base_url}/api/health")
        return response.json()

    def get_all_tasks(self) -> dict:
        response = requests.get(f"{self.base_url}/api/tasks")
        return response.json()

    def get_task(self, task_id: str) -> dict:
        response = requests.get(f"{self.base_url}/api/tasks/{task_id}")
        return response.json()

    def get_task_progress(self, task_id: str) -> dict:
        response = requests.get(f"{self.base_url}/api/tasks/{task_id}/progress")
        return response.json()

    def cleanup_tasks(self, days: int = 7) -> dict:
        response = requests.post(
            f"{self.base_url}/api/tasks/cleanup",
            json={"days": days}
        )
        return response.json()

    def wait_for_task_completion(self, task_id: str, poll_interval: float = 1.0, timeout: Optional[float] = None) -> dict:
        start_time = time.time()

        while True:
            result = self.get_task_progress(task_id)

            if not result.get('success'):
                return result

            data = result.get('data', {})
            status = data.get('status')
            progress = data.get('progress', 0)

            if status == 'completed':
                return result
            elif status == 'failed':
                return result

            if timeout and (time.time() - start_time) > timeout:
                return {
                    'success': False,
                    'error': f'等待超时（{timeout}秒）',
                    'data': data
                }

            time.sleep(poll_interval)


def test_progress_query_api():
    print("="*80)
    print("进度查询API功能测试")
    print("="*80)

    client = ProgressQueryClient()

    print("\n[测试1] 健康检查")
    print("-"*80)
    try:
        health = client.health_check()
        print(f"状态: {health.get('status')}")
        print(f"时间: {health.get('timestamp')}")
        print("✓ 健康检查通过")
    except Exception as e:
        print(f"✗ 健康检查失败: {e}")
        return False

    print("\n[测试2] 获取所有任务")
    print("-"*80)
    try:
        all_tasks = client.get_all_tasks()
        print(f"任务数量: {all_tasks.get('count', 0)}")
        print("✓ 获取所有任务成功")
    except Exception as e:
        print(f"✗ 获取所有任务失败: {e}")
        return False

    print("\n[测试3] 查询无效任务ID")
    print("-"*80)
    try:
        invalid_task_id = "invalid-task-id-12345"
        result = client.get_task(invalid_task_id)
        if not result.get('success'):
            print(f"错误信息: {result.get('error')}")
            print("✓ 正确处理无效任务ID")
        else:
            print("✗ 应该返回错误")
            return False
    except Exception as e:
        print(f"✗ 查询无效任务ID测试失败: {e}")
        return False

    print("\n[测试4] 查询无效任务ID的进度")
    print("-"*80)
    try:
        result = client.get_task_progress(invalid_task_id)
        if not result.get('success'):
            print(f"错误信息: {result.get('error')}")
            print("✓ 正确处理无效任务ID进度查询")
        else:
            print("✗ 应该返回错误")
            return False
    except Exception as e:
        print(f"✗ 查询无效任务ID进度测试失败: {e}")
        return False

    print("\n[测试5] 清理旧任务")
    print("-"*80)
    try:
        result = client.cleanup_tasks(days=0)
        if result.get('success'):
            print(f"清理任务数: {result.get('data', {}).get('deleted_count', 0)}")
            print("✓ 清理旧任务成功")
        else:
            print(f"✗ 清理失败: {result.get('error')}")
            return False
    except Exception as e:
        print(f"✗ 清理旧任务测试失败: {e}")
        return False

    print("\n" + "="*80)
    print("✅ 所有测试通过！")
    print("="*80)
    return True


def monitor_task_progress(task_id: str):
    print("\n" + "="*80)
    print("任务进度监控测试")
    print("="*80)

    client = ProgressQueryClient()

    print(f"\n任务ID: {task_id}")
    print("开始监控任务进度...")
    print("-"*80)

    last_progress = -1
    poll_count = 0

    try:
        while True:
            result = client.get_task_progress(task_id)

            if not result.get('success'):
                print(f"✗ 查询失败: {result.get('error')}")
                break

            data = result.get('data', {})
            status = data.get('status')
            progress = data.get('progress', 0)
            current_step = data.get('current_step', '')

            poll_count += 1

            if progress != last_progress:
                print(f"[查询 #{poll_count}] 状态: {status} | 进度: {progress:.1f}% | 步骤: {current_step}")
                last_progress = progress

            if status == 'completed':
                print("\n✅ 任务完成！")
                break
            elif status == 'failed':
                error_msg = data.get('error_message', '未知错误')
                print(f"\n✗ 任务失败: {error_msg}")
                break

            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\n用户中断监控")
    except Exception as e:
        print(f"\n✗ 监控过程中发生错误: {e}")

    print("="*80)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        task_id = sys.argv[1]
        monitor_task_progress(task_id)
    else:
        test_progress_query_api()
