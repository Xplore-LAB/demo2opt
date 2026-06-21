"""国际化支持"""
from typing import Dict


class I18n:
    """国际化文本映射"""
    
    COMMON_PHRASES = {
        "Energy and extraction indicators may be coupled.": "能耗指标与提取率指标可能存在耦合关系。",
        "Stability metrics are low and may affect performance.": "稳定性指标偏低，可能影响系统性能。",
        "No strong coupling identified.": "未识别到显著耦合关系。",
        "No analyzable abnormal data detected.": "未检测到可分析的异常数据。",
        "Keep current operation and continue monitoring.": "建议维持当前工况并持续监测。",
        "No extra warning.": "当前无额外安全警告。",
        "Input data is empty.": "输入数据为空。",
        "Need manual review before execution.": "执行前需人工复核。",
        "Use standard procedures and interlock constraints.": "请遵循标准操作规程并严格满足联锁约束。",
    }
    
    @classmethod
    def localize(cls, text: str) -> str:
        """本地化文本"""
        if not text:
            return text
        output = text
        for en, zh in cls.COMMON_PHRASES.items():
            output = output.replace(en, zh)
        return output
