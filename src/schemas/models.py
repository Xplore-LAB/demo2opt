from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum
import pandas as pd

class SensorDataModel(BaseModel):
    tag_id: str = Field(..., description="传感器标签ID")
    name: Optional[str] = Field(None, description="传感器描述名称")
    value: float = Field(..., description="当前传感器值", ge=-999999, le=999999)
    unit: Optional[str] = Field("", description="单位")
    design_ref: Optional[float] = Field(None, description="设计参考值", ge=-999999, le=999999)
    timestamp: Optional[str] = Field(None, description="时间戳")

    @field_validator('value')
    @classmethod
    def validate_value(cls, v):
        if v is None:
            raise ValueError('传感器值不能为空')
        return v

    @field_validator('tag_id')
    @classmethod
    def validate_tag_id(cls, v):
        if not v or not v.strip():
            raise ValueError('标签ID不能为空')
        return v.strip()

class MembershipDataModel(BaseModel):
    name: str = Field(..., description="指标名称")
    current_value: float = Field(..., description="当前值")
    membership_degree: float = Field(..., ge=0.0, le=1.0, description="隶属度值 [0,1]")
    semantic_state: str = Field(..., description="语义状态")

    @field_validator('semantic_state')
    @classmethod
    def validate_semantic_state(cls, v):
        valid_states = ['优秀', '良好', '一般', '较差', '差', '异常', '偏差较大', '偏离显著']
        if v not in valid_states:
            raise ValueError(f'语义状态必须是以下之一: {valid_states}')
        return v

class CoreIndicatorsModel(BaseModel):
    extraction_rate: Dict[str, Dict[str, Any]] = Field(..., description="提取率指标")
    stability: Dict[str, Dict[str, Any]] = Field(..., description="稳定性指标")
    energy_consumption: Dict[str, Dict[str, Any]] = Field(..., description="单耗指标")

class SemanticDataModel(BaseModel):
    tag_id: Optional[str] = Field(None, description="指标标签ID")
    name: str = Field(..., description="指标名称")
    current_value: float = Field(..., description="当前值")
    state_desc: str = Field(..., description="状态描述")
    diff: float = Field(..., description="与设计值的偏差")
    membership_degree: Optional[float] = Field(None, ge=0.0, le=1.0, description="隶属度值")
    semantic_state: Optional[str] = Field(None, description="语义状态")
    assessment_reason: Optional[str] = Field(None, description="规则层对该指标好坏的判断说明")
    comparison_summary: Optional[str] = Field(None, description="设计值、历史优值与经验标杆的比较摘要")
    reference_label: Optional[str] = Field(None, description="当前偏差采用的参考基准名称")
    reference_value: Optional[float] = Field(None, description="当前偏差采用的参考基准值")
    reference_source_type: Optional[str] = Field(None, description="参考值来源类型")
    reference_source_label: Optional[str] = Field(None, description="参考值来源说明")
    reference_scope: Optional[str] = Field(None, description="参考值适用范围")
    comparison_method: Optional[str] = Field(None, description="当前偏差比较口径")
    reference_basis_kind: Optional[str] = Field(None, description="参考值来源性质")
    reference_basis_text: Optional[str] = Field(None, description="参考值来源说明正文")
    applicable_scope: Optional[str] = Field(None, description="参考值适用对象")
    applicable_conditions: Optional[str] = Field(None, description="参考值适用边界")
    reference_owner: Optional[str] = Field(None, description="参考值维护责任方")
    last_reviewed_at: Optional[str] = Field(None, description="参考值最近复核日期")
    validation_status: Optional[str] = Field(None, description="参考值成熟度状态")
    standby_context: Optional[Dict[str, Any]] = Field(None, description="主备/待机判读上下文")

    @field_validator('state_desc')
    @classmethod
    def validate_state_desc(cls, v):
        valid_states = ['正常', '偏高', '偏低', '严重偏高', '严重偏低', 'Unknown', '优秀', '良好', '一般', '较差', '差', '异常', '偏差较大', '偏离显著', '待机备用']
        if v not in valid_states:
            raise ValueError(f'状态描述必须是以下之一: {valid_states}')
        return v

class IndicatorDiagnosisModel(BaseModel):
    name: str = Field(..., description="异常指标名称")
    ai_reason: str = Field(..., description="AI 对该指标的简短复核原因")
    confidence: Optional[str] = Field(None, description="原因置信度")

    @field_validator('name', 'ai_reason', mode='before')
    @classmethod
    def validate_indicator_text(cls, v):
        if isinstance(v, list):
            v = "\n".join([str(item) for item in v])
        if v is None:
            raise ValueError('字段不能为空')
        text = str(v).strip()
        if not text:
            raise ValueError('字段不能为空')
        return text


def downgrade_root_cause_claims(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return text
    replacements = [
        ("已确认根因", "待核查假设"),
        ("根因已锁定", "疑似根因链待现场确认"),
        ("已锁定根因链起点", "疑似根因链起点"),
        ("锁定根因链起点", "疑似根因链起点"),
        ("已锁定根因", "疑似根因链待现场确认"),
        ("核心根因", "主导异常"),
        ("锁定根因", "收敛到疑似根因链"),
    ]
    for old, new in replacements:
        text = text.replace(old, new)
    return text

class ReasoningResultModel(BaseModel):
    root_cause: str = Field(..., description="根本原因分析")
    operation_suggestion: str = Field(..., description="操作建议")
    safety_warning: str = Field(..., description="安全警告")
    thought_process: Optional[str] = Field(None, description="思考过程（Chain of Thought）")
    bottleneck_indicators: Optional[List[str]] = Field(default_factory=list, description="瓶颈指标列表")
    coupling_analysis: Optional[str] = Field(None, description="耦合关系分析")
    missing_data_request: Optional[Dict[str, Any]] = Field(None, description="S6 缺口数据主动询问")
    indicator_diagnoses: Optional[List[IndicatorDiagnosisModel]] = Field(default_factory=list, description="按指标输出的 AI 复核原因")
    raw_response: Optional[str] = Field(None, description="原始大模型响应内容")

    @field_validator('root_cause', 'operation_suggestion', 'safety_warning', mode='before')
    @classmethod
    def validate_not_empty(cls, v):
        if isinstance(v, list):
            v = "\n".join([str(item) for item in v])
        
        if not isinstance(v, str):
            v = str(v)
             
        if not v or not v.strip():
            raise ValueError('字段不能为空')
        return v.strip()

    @field_validator('root_cause', mode='before')
    @classmethod
    def downgrade_root_cause_text(cls, v):
        if isinstance(v, list):
            v = "\n".join([str(item) for item in v])
        return downgrade_root_cause_claims(v)

class DecisionResultModel(BaseModel):
    actionable_steps: str = Field(..., description="可执行步骤")
    simulation_result: str = Field(..., description="模拟预测结果")
    verification_status: str = Field(..., description="验证状态")
    reasoning_summary: str = Field(..., description="推理摘要")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="置信度分数")
    risk_assessment: Optional[str] = Field(None, description="S7 风险评估")
    rollback_strategy: Optional[str] = Field(None, description="S7 回退策略")

    @field_validator('verification_status')
    @classmethod
    def validate_status(cls, v):
        valid_statuses = ['Passed', 'Failed', 'Pending']
        if v not in valid_statuses:
            raise ValueError(f'验证状态必须是以下之一: {valid_statuses}')
        return v

class AnalysisReportModel(BaseModel):
    timestamp: str = Field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    status: str = Field(..., description="分析状态")
    abnormal_count: int = Field(..., ge=0, description="异常指标数量")
    semantic_data: List[SemanticDataModel] = Field(default_factory=list, description="语义数据")
    core_indicators: Optional[CoreIndicatorsModel] = Field(None, description="核心指标")
    reasoning_result: Optional[ReasoningResultModel] = Field(None, description="推理结果")
    decision_result: Optional[DecisionResultModel] = Field(None, description="决策结果")
    error: Optional[str] = Field(None, description="错误信息")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        valid_statuses = ['healthy', 'abnormal', 'error']
        if v not in valid_statuses:
            raise ValueError(f'状态必须是以下之一: {valid_statuses}')
        return v


def validate_sensor_data(data_list: List[dict]) -> List[SensorDataModel]:
    """验证传感器数据列表"""
    validated_data = []
    errors = []

    for idx, data in enumerate(data_list):
        try:
            validated = SensorDataModel(**data)
            validated_data.append(validated)
        except Exception as e:
            errors.append(f"数据项 {idx}: {str(e)}")

    if errors:
        print(f"警告: 发现 {len(errors)} 条数据验证错误")
        for error in errors[:5]:
            print(f"  - {error}")
        if len(errors) > 5:
            print(f"  ... 还有 {len(errors) - 5} 条错误")

    return validated_data


def validate_semantic_data(data_list: List[dict]) -> List[SemanticDataModel]:
    """验证语义数据列表"""
    validated_data = []
    for data in data_list:
        try:
            validated = SemanticDataModel(**data)
            validated_data.append(validated)
        except Exception as e:
            print(f"警告: 语义数据验证失败: {str(e)}")
    return validated_data


def validate_reasoning_result(data: dict) -> ReasoningResultModel:
    """验证推理结果"""
    try:
        return ReasoningResultModel(**data)
    except Exception as e:
        print(f"警告: 推理结果验证失败: {str(e)}")
        return ReasoningResultModel(
            root_cause=data.get('root_cause', '未知'),
            operation_suggestion=data.get('operation_suggestion', '无建议'),
            safety_warning=data.get('safety_warning', '无警告'),
            thought_process=data.get('thought_process'),
            knowledge_references=data.get('knowledge_references', []),
            missing_data_request=data.get('missing_data_request'),
            raw_response=data.get('raw_response')
        )


def validate_decision_result(data: dict) -> DecisionResultModel:
    """验证决策结果"""
    try:
        return DecisionResultModel(**data)
    except Exception as e:
        print(f"警告: 决策结果验证失败: {str(e)}")
        return DecisionResultModel(
            actionable_steps=data.get('actionable_steps', '无步骤'),
            simulation_result=data.get('simulation_result', '无预测'),
            verification_status=data.get('verification_status', 'Pending'),
            reasoning_summary=data.get('reasoning_summary', '无摘要'),
            confidence_score=data.get('confidence_score'),
            risk_assessment=data.get('risk_assessment'),
            rollback_strategy=data.get('rollback_strategy')
        )


def model_to_dict(model):
    """将 Pydantic 模型转换为字典（兼容 Pydantic V2）"""
    if hasattr(model, 'model_dump'):
        return model.model_dump()
    else:
        return model.dict()


class ASUTagModel(BaseModel):
    tag_code: str = Field(..., description="标签代码")
    tag_name_cn: str = Field(..., description="中文名称")
    unit: str = Field(..., description="单位")
    unit_confidence: str = Field(..., description="单位置信度")
    unified_field: str = Field(..., description="统一字段名")
    used_in_current_scope: bool = Field(..., description="是否在当前范围内使用")
    kpi_role: str = Field(..., description="KPI角色")
    notes: Optional[str] = Field(None, description="备注")


class ASUFactModel(BaseModel):
    time: datetime = Field(..., description="时间戳")
    tag_code: str = Field(..., description="标签代码")
    unified_field: str = Field(..., description="统一字段名")
    value: float = Field(..., description="数值")
    tag_name_cn: Optional[str] = Field(None, description="中文名称")
    unit: Optional[str] = Field(None, description="单位")
    kpi_role: Optional[str] = Field(None, description="KPI角色")


class ASUDerivedMetricModel(BaseModel):
    metric_code: str = Field(..., description="指标代码")
    name_cn: str = Field(..., description="中文名称")
    unit: str = Field(..., description="单位")
    type: str = Field(..., description="类型")
    formula: str = Field(..., description="计算公式")
    inputs: List[str] = Field(..., description="输入字段列表")
    quality: Dict[str, Any] = Field(default_factory=dict, description="质量控制规则")


class ASUDerivedResultModel(BaseModel):
    time: datetime = Field(..., description="时间戳")
    metric_code: str = Field(..., description="指标代码")
    value: float = Field(..., description="数值")
    quality_flags: Optional[str] = Field(None, description="质量标志")

    @field_validator('quality_flags', mode='before')
    @classmethod
    def validate_quality_flags(cls, v):
        if pd.isna(v):
            return None
        return str(v) if v is not None else None


class ASUPipelineResultModel(BaseModel):
    facts: List[ASUFactModel] = Field(default_factory=list, description="原始数据")
    meta: List[ASUTagModel] = Field(default_factory=list, description="元数据")
    derived: List[ASUDerivedResultModel] = Field(default_factory=list, description="衍生指标")
    quality: Dict[str, Any] = Field(default_factory=dict, description="质量信息")


class MetricQualityPolicy(str, Enum):
    ANY_MISSING_TO_MISSING = "any_missing->missing"
    ALL_MISSING_TO_MISSING = "all_missing->missing"
    IGNORE_MISSING = "ignore_missing"


class MetricRangeCheck(BaseModel):
    field: str = Field(..., description="字段名")
    condition: str = Field(..., description="条件表达式")
    on_fail: str = Field(..., description="失败时的处理方式")


class MetricQualityRule(BaseModel):
    missing_policy: MetricQualityPolicy = Field(..., description="缺失值处理策略")
    range_check: Optional[str] = Field(None, description="范围检查规则")
    div0_policy: Optional[str] = Field(None, description="除零处理策略")
    eps: Optional[float] = Field(1e-6, description="极小值阈值")


def validate_asu_tags(data_list: List[dict]) -> List[ASUTagModel]:
    """验证ASU标签数据列表"""
    validated_data = []
    for data in data_list:
        try:
            validated = ASUTagModel(**data)
            validated_data.append(validated)
        except Exception as e:
            print(f"警告: ASU标签数据验证失败: {str(e)}")
    return validated_data


def validate_asu_facts(data_list: List[dict]) -> List[ASUFactModel]:
    """验证ASU事实数据列表"""
    validated_data = []
    for data in data_list:
        try:
            validated = ASUFactModel(**data)
            validated_data.append(validated)
        except Exception as e:
            print(f"警告: ASU事实数据验证失败: {str(e)}")
    return validated_data


def validate_asu_derived(data_list: List[dict]) -> List[ASUDerivedResultModel]:
    """验证ASU衍生指标数据列表"""
    validated_data = []
    for data in data_list:
        try:
            validated = ASUDerivedResultModel(**data)
            validated_data.append(validated)
        except Exception as e:
            print(f"警告: ASU衍生指标数据验证失败: {str(e)}")
    return validated_data
