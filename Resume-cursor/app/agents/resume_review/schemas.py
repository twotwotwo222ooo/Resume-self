from pydantic import BaseModel, ConfigDict, Field


class DimensionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100, description="该维整数分，0–100")
    comment: str = Field(min_length=1, description="给分理由，必须点名 evidence 中的锚点 ID")
    evidence: list[str] = Field(
        min_length=1,
        max_length=8,
        description="只填锚点 ID，如 项目经历-3、工作经历-2，不要带方括号，不要填子块正文",
    )


class Scores(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_depth: DimensionScore = Field(description="项目深度")
    tech_match: DimensionScore = Field(description="技术匹配度")
    expression: DimensionScore = Field(description="表达规范性")
    structure: DimensionScore = Field(description="简历结构")
    quantification: DimensionScore = Field(description="量化程度")
    credibility: DimensionScore = Field(description="真实可信度")


class JobFit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=100, description="岗位匹配整数分，0–100；无 JD 或仅有岗位名时最高 69；不计入综合分")
    comment: str = Field(min_length=1, description="匹配度说明；无 JD 须写「未提供目标岗位」，仅有岗位名须写「仅有岗位名称、无 JD」")


class Summary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    highlights: list[str] = Field(
        min_length=2,
        max_length=4,
        description="2–4 条核心亮点，每条点名至少一个锚点 ID",
    )
    improvements: list[str] = Field(
        min_length=3,
        max_length=5,
        description="3–5 条改进，格式：原句（锚点ID）→ 改后句，改后句须具体并尽量带数字",
    )
    overall_comment: str = Field(min_length=40, description="综合评语，说明层级、短板和先改哪一块")
    job_fit: JobFit


class LLMReport(BaseModel):
    model_config = ConfigDict(extra="ignore")

    scores: Scores
    summary: Summary


class ExtractedEducation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    school: str = Field(default="", description="学校，无法提取则为空字符串")
    major: str = Field(default="", description="专业，无法提取则为空字符串")
    degree: str = Field(default="", description="学历，无法提取则为空字符串")
    time_range: str = Field(default="", description="时间，格式 YYYY.MM - YYYY.MM，至今则保留至今")


class ExtractedExperience(BaseModel):
    model_config = ConfigDict(extra="ignore")

    company: str = Field(default="", description="公司或组织，无法提取则为空字符串")
    title: str = Field(default="", description="职位，无法提取则为空字符串")
    time_range: str = Field(default="", description="时间，格式 YYYY.MM - YYYY.MM，至今则保留至今")
    description: str = Field(default="", description="职责原文，不要改写或压缩")
    tech_stack: list[str] = Field(default_factory=list, description="技术栈，每项单独一个")
    quantified_highlights: list[str] = Field(default_factory=list, description="仅含数字的原文子块")


class ExtractedProject(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(default="", description="项目名称，无法提取则为空字符串")
    role: str = Field(default="", description="个人角色，无法提取则为空字符串")
    time_range: str = Field(default="", description="时间，格式 YYYY.MM - YYYY.MM，至今则保留至今")
    description: str = Field(default="", description="项目描述原文，不要改写或压缩")
    tech_stack: list[str] = Field(default_factory=list, description="技术栈，每项单独一个，如 Spring Boot、MySQL")
    quantified_highlights: list[str] = Field(default_factory=list, description="仅含数字的原文子块")


class ResumeExtract(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = Field(default="", description="姓名，无法提取则为空字符串")
    education: list[ExtractedEducation] = Field(default_factory=list)
    experiences: list[ExtractedExperience] = Field(default_factory=list, description="工作或实习经历")
    projects: list[ExtractedProject] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="技能，每项单独一个")
    quantified_highlights: list[str] = Field(
        default_factory=list,
        description="全文中含数字的量化亮点子块原文，如 提升30%、10万DAU",
    )


SCORE_WEIGHTS: dict[str, float] = {
    "project_depth": 0.25,
    "tech_match": 0.25,
    "quantification": 0.15,
    "credibility": 0.15,
    "expression": 0.10,
    "structure": 0.10,
}


def clamp_score(value: int) -> int:
    return max(0, min(100, int(value)))


def weighted_overall(scores: Scores) -> int:
    total = 0.0
    mapping = scores.model_dump()
    for key, weight in SCORE_WEIGHTS.items():
        total += clamp_score(mapping[key]["score"]) * weight
    return int(round(total))
