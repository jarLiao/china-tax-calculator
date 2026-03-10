#!/usr/bin/env python3
"""
中国个人所得税计算器 - 2025年版
支持月度工资、年终奖、专项附加扣除、年度汇算清缴、多收入来源计算
"""

from dataclasses import dataclass, field
from typing import Optional, List, Dict
from enum import Enum

# ==================== 税率表 ====================

# 综合所得月度税率表（累计预扣法）
MONTHLY_TAX_BRACKETS = [
    (3000, 0.03, 0),
    (12000, 0.10, 210),
    (25000, 0.20, 1410),
    (35000, 0.25, 2660),
    (55000, 0.30, 4410),
    (80000, 0.35, 7160),
    (float('inf'), 0.45, 15160),
]

# 综合所得年度税率表（汇算清缴用）
ANNUAL_TAX_BRACKETS = [
    (36000, 0.03, 0),
    (144000, 0.10, 2520),
    (300000, 0.20, 16920),
    (420000, 0.25, 31920),
    (660000, 0.30, 52920),
    (960000, 0.35, 85920),
    (float('inf'), 0.45, 181920),
]

# 年终奖税率表（按月均额）
BONUS_TAX_BRACKETS = [
    (3000, 0.03, 0),
    (12000, 0.10, 210),
    (25000, 0.20, 1410),
    (35000, 0.25, 2660),
    (55000, 0.30, 4410),
    (80000, 0.35, 7160),
    (float('inf'), 0.45, 15160),
]

# 起征点
THRESHOLD = 5000
ANNUAL_THRESHOLD = 60000


# ==================== 数据类 ====================

@dataclass
class SpecialDeduction:
    """专项附加扣除"""
    children_education: int = 0      # 子女教育（2000元/孩/月）
    infant_care: int = 0             # 3岁以下婴幼儿照护（2000元/孩/月）
    continuing_education: int = 0    # 继续教育（400元/月）
    serious_illness: int = 0         # 大病医疗（年度，最高80000）
    housing_loan: int = 0            # 住房贷款利息（1000元/月）
    housing_rent: int = 0            # 住房租金（800-1500元/月）
    elderly_support: int = 0         # 赡养老人（独生3000，非独生最高1500）

    @property
    def total_monthly(self) -> int:
        """月度专项附加扣除总额"""
        return (
            self.children_education +
            self.infant_care +
            self.continuing_education +
            self.housing_loan +
            self.housing_rent +
            self.elderly_support
        )


@dataclass
class MonthlyTaxResult:
    """月度个税计算结果"""
    month: int
    gross_income: float              # 税前收入
    social_insurance: float          # 五险一金
    special_deduction: float         # 专项附加扣除
    taxable_income: float            # 应纳税所得额
    tax_rate: float                  # 税率
    quick_deduction: float           # 速算扣除数
    monthly_tax: float               # 本月应纳税额
    cumulative_tax: float            # 累计应纳税额
    net_income: float                # 税后收入


@dataclass
class BonusTaxResult:
    """年终奖计税结果"""
    bonus: float                     # 年终奖金额
    method: str                      # 计税方式：separate/combined
    monthly_average: float           # 月均额（单独计税）
    tax_rate: float                  # 税率
    quick_deduction: float           # 速算扣除数
    tax: float                       # 应纳税额
    net_bonus: float                 # 税后年终奖


@dataclass
class IncomeSource:
    """多收入来源"""
    salary: float = 0                # 工资薪金（年度总额）
    labor_income: float = 0          # 劳务报酬（年度总额，扣除20%费用）
    royalty_income: float = 0        # 稿酬（年度总额，扣除20%费用后减按70%）
    franchise_income: float = 0      # 特许权使用费（年度总额，扣除20%费用）
    
    @property
    def total_comprehensive_income(self) -> float:
        """
        计算综合所得总额
        - 工资薪金：全额计入
        - 劳务报酬：收入 × (1 - 20%)
        - 稿酬：收入 × (1 - 20%) × 70%
        - 特许权使用费：收入 × (1 - 20%)
        """
        return (
            self.salary +
            self.labor_income * 0.8 +
            self.royalty_income * 0.8 * 0.7 +
            self.franchise_income * 0.8
        )


@dataclass
class AnnualSettlementResult:
    """年度汇算清缴结果"""
    comprehensive_income: float      # 综合所得总额
    deductions: float                # 各项扣除总额
    taxable_income: float            # 应纳税所得额
    tax_rate: float                  # 税率
    quick_deduction: float           # 速算扣除数
    annual_tax: float                # 年度应纳税额
    prepaid_tax: float               # 已预缴税额
    settlement_amount: float         # 汇算金额（正数=应补缴，负数=应退税）
    
    @property
    def is_refund(self) -> bool:
        """是否退税"""
        return self.settlement_amount < 0
    
    @property
    def status_text(self) -> str:
        """状态文本"""
        if self.settlement_amount > 0:
            return f"应补缴 ¥{self.settlement_amount:,.2f}"
        elif self.settlement_amount < 0:
            return f"应退税 ¥{abs(self.settlement_amount):,.2f}"
        else:
            return "无需补退"


@dataclass
class BonusOptimizationResult:
    """年终奖优化结果"""
    total_bonus: float               # 年终奖总额
    optimal_split: List[Dict]        # 最优分配方案
    total_tax: float                 # 最优方案总税额
    worst_tax: float                 # 最差方案总税额
    savings: float                   # 节省税额


# ==================== 计算函数 ====================

def get_tax_info(taxable: float, brackets: list) -> tuple:
    """根据应纳税所得额获取税率和速算扣除数"""
    for upper, rate, quick_ded in brackets:
        if taxable <= upper:
            return rate, quick_ded
    return 0.45, 15160


def calculate_monthly_tax(
    monthly_salary: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
    month: int = 1,
    cumulative_income: float = 0,
    cumulative_social: float = 0,
    cumulative_deduction: float = 0,
    cumulative_tax_paid: float = 0,
) -> MonthlyTaxResult:
    """
    计算月度个税（累计预扣法）

    Args:
        monthly_salary: 月税前工资
        social_insurance: 月五险一金（个人部分）
        special_deduction: 专项附加扣除
        month: 当前月份（1-12）
        cumulative_income: 累计收入
        cumulative_social: 累计五险一金
        cumulative_deduction: 累计专项附加扣除
        cumulative_tax_paid: 累计已缴税额

    Returns:
        MonthlyTaxResult: 月度个税计算结果
    """
    # 累计值
    cum_income = cumulative_income + monthly_salary
    cum_social = cumulative_social + social_insurance
    cum_deduction = cumulative_deduction + special_deduction.total_monthly

    # 累计应纳税所得额
    cum_taxable = cum_income - cum_social - cum_deduction - THRESHOLD * month
    cum_taxable = max(0, cum_taxable)

    # 获取税率
    tax_rate, quick_ded = get_tax_info(cum_taxable, MONTHLY_TAX_BRACKETS)

    # 累计应纳税额
    cum_tax = cum_taxable * tax_rate - quick_ded

    # 本月应纳税额
    monthly_tax = cum_tax - cumulative_tax_paid
    monthly_tax = max(0, monthly_tax)

    # 本月应纳税所得额
    monthly_taxable = cum_taxable - (cumulative_income - cumulative_social - cumulative_deduction - THRESHOLD * (month - 1))

    return MonthlyTaxResult(
        month=month,
        gross_income=monthly_salary,
        social_insurance=social_insurance,
        special_deduction=special_deduction.total_monthly,
        taxable_income=monthly_taxable,
        tax_rate=tax_rate,
        quick_deduction=quick_ded,
        monthly_tax=monthly_tax,
        cumulative_tax=cum_tax,
        net_income=monthly_salary - social_insurance - monthly_tax,
    )


def calculate_annual_tax(
    monthly_salary: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
    months: int = 12,
) -> List[MonthlyTaxResult]:
    """
    计算全年个税（逐月）

    Args:
        monthly_salary: 月税前工资
        social_insurance: 月五险一金
        special_deduction: 专项附加扣除
        months: 计算月数（默认12）

    Returns:
        List[MonthlyTaxResult]: 每月的个税计算结果
    """
    results = []
    cum_income = 0
    cum_social = 0
    cum_deduction = 0
    cum_tax = 0

    for month in range(1, months + 1):
        result = calculate_monthly_tax(
            monthly_salary=monthly_salary,
            social_insurance=social_insurance,
            special_deduction=special_deduction,
            month=month,
            cumulative_income=cum_income,
            cumulative_social=cum_social,
            cumulative_deduction=cum_deduction,
            cumulative_tax_paid=cum_tax,
        )
        results.append(result)

        # 更新累计值
        cum_income += monthly_salary
        cum_social += social_insurance
        cum_deduction += special_deduction.total_monthly
        cum_tax = result.cumulative_tax

    return results


def calculate_bonus_separate(bonus: float) -> BonusTaxResult:
    """
    年终奖单独计税

    Args:
        bonus: 年终奖金额

    Returns:
        BonusTaxResult: 计税结果
    """
    # 月均额
    monthly_avg = bonus / 12

    # 获取税率
    tax_rate, quick_ded = get_tax_info(monthly_avg, BONUS_TAX_BRACKETS)

    # 应纳税额
    tax = bonus * tax_rate - quick_ded

    return BonusTaxResult(
        bonus=bonus,
        method="separate",
        monthly_average=monthly_avg,
        tax_rate=tax_rate,
        quick_deduction=quick_ded,
        tax=tax,
        net_bonus=bonus - tax,
    )


def calculate_bonus_combined(
    bonus: float,
    monthly_salary: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
) -> BonusTaxResult:
    """
    年终奖合并计税（并入综合所得）

    Args:
        bonus: 年终奖金额
        monthly_salary: 月工资
        social_insurance: 月五险一金
        special_deduction: 专项附加扣除

    Returns:
        BonusTaxResult: 计税结果
    """
    # 计算不含年终奖的年度个税
    annual_results = calculate_annual_tax(
        monthly_salary=monthly_salary,
        social_insurance=social_insurance,
        special_deduction=special_deduction,
    )
    tax_without_bonus = annual_results[-1].cumulative_tax

    # 计算含年终奖的年度个税（假设年终奖在12月发放）
    annual_income = monthly_salary * 12 + bonus
    annual_social = social_insurance * 12
    annual_deduction = special_deduction.total_monthly * 12

    annual_taxable = annual_income - annual_social - annual_deduction - THRESHOLD * 12
    annual_taxable = max(0, annual_taxable)

    tax_rate, quick_ded = get_tax_info(annual_taxable, MONTHLY_TAX_BRACKETS)
    tax_with_bonus = annual_taxable * tax_rate - quick_ded

    # 年终奖部分税额
    bonus_tax = tax_with_bonus - tax_without_bonus

    return BonusTaxResult(
        bonus=bonus,
        method="combined",
        monthly_average=0,
        tax_rate=tax_rate,
        quick_deduction=quick_ded,
        tax=bonus_tax,
        net_bonus=bonus - bonus_tax,
    )


def compare_bonus_methods(
    bonus: float,
    monthly_salary: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
) -> Dict:
    """
    对比年终奖单独计税和合并计税

    Args:
        bonus: 年终奖金额
        monthly_salary: 月工资
        social_insurance: 月五险一金
        special_deduction: 专项附加扣除

    Returns:
        Dict: 对比结果
    """
    separate = calculate_bonus_separate(bonus)
    combined = calculate_bonus_combined(
        bonus, monthly_salary, social_insurance, special_deduction
    )

    return {
        "separate": separate,
        "combined": combined,
        "recommendation": "separate" if separate.tax <= combined.tax else "combined",
        "savings": abs(separate.tax - combined.tax),
    }


def reverse_gross_from_net(
    target_net: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
    max_iterations: int = 100,
) -> float:
    """
    从税后收入反推税前收入

    Args:
        target_net: 目标税后收入
        social_insurance: 五险一金
        special_deduction: 专项附加扣除
        max_iterations: 最大迭代次数

    Returns:
        float: 税前收入
    """
    # 初始估计
    gross = target_net + social_insurance

    for _ in range(max_iterations):
        # 计算当前估计的税后
        result = calculate_monthly_tax(
            monthly_salary=gross,
            social_insurance=social_insurance,
            special_deduction=special_deduction,
        )
        current_net = result.net_income

        # 差值
        diff = target_net - current_net

        # 收敛判断
        if abs(diff) < 0.01:
            return gross

        # 调整估计（考虑税率影响）
        gross += diff / (1 - result.tax_rate) if result.tax_rate < 1 else diff

    return gross


# ==================== 年度汇算清缴 ====================

def calculate_annual_settlement(
    income_sources: IncomeSource,
    annual_social_insurance: float,
    special_deduction: SpecialDeduction,
    other_deductions: float = 0,
    prepaid_tax: float = 0,
) -> AnnualSettlementResult:
    """
    计算年度汇算清缴

    Args:
        income_sources: 多收入来源
        annual_social_insurance: 年度五险一金（个人部分）
        special_deduction: 专项附加扣除
        other_deductions: 其他扣除（企业年金、商业健康保险等）
        prepaid_tax: 已预缴税额

    Returns:
        AnnualSettlementResult: 汇算清缴结果
    """
    # 综合所得总额
    comprehensive_income = income_sources.total_comprehensive_income
    
    # 各项扣除总额
    total_deductions = (
        annual_social_insurance +
        special_deduction.total_monthly * 12 +
        other_deductions +
        ANNUAL_THRESHOLD
    )
    
    # 应纳税所得额
    taxable_income = max(0, comprehensive_income - total_deductions)
    
    # 获取税率
    tax_rate, quick_ded = get_tax_info(taxable_income, ANNUAL_TAX_BRACKETS)
    
    # 年度应纳税额
    annual_tax = taxable_income * tax_rate - quick_ded
    
    # 汇算金额（正数=应补缴，负数=应退税）
    settlement_amount = annual_tax - prepaid_tax
    
    return AnnualSettlementResult(
        comprehensive_income=comprehensive_income,
        deductions=total_deductions,
        taxable_income=taxable_income,
        tax_rate=tax_rate,
        quick_deduction=quick_ded,
        annual_tax=annual_tax,
        prepaid_tax=prepaid_tax,
        settlement_amount=settlement_amount,
    )


# ==================== 年终奖智能优化 ====================

def optimize_bonus_allocation(
    total_bonus: float,
    monthly_salary: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
    max_splits: int = 5,
) -> BonusOptimizationResult:
    """
    年终奖智能优化 - 找到最优的年终奖分配方案
    
    策略：
    1. 部分并入当月工资，部分单独计税
    2. 或分多次发放
    3. 找到总税额最小的方案

    Args:
        total_bonus: 年终奖总额
        monthly_salary: 月工资
        social_insurance: 月五险一金
        special_deduction: 专项附加扣除
        max_splits: 最多分几次发放

    Returns:
        BonusOptimizationResult: 优化结果
    """
    optimal_split = []
    min_tax = float('inf')
    max_tax = 0
    
    # 方案1：全部单独计税
    separate = calculate_bonus_separate(total_bonus)
    if separate.tax < min_tax:
        min_tax = separate.tax
        optimal_split = [{"amount": total_bonus, "method": "单独计税", "tax": separate.tax}]
    max_tax = max(max_tax, separate.tax)
    
    # 方案2：全部合并计税
    combined = calculate_bonus_combined(
        total_bonus, monthly_salary, social_insurance, special_deduction
    )
    if combined.tax < min_tax:
        min_tax = combined.tax
        optimal_split = [{"amount": total_bonus, "method": "合并计税", "tax": combined.tax}]
    max_tax = max(max_tax, combined.tax)
    
    # 方案3：部分单独 + 部分合并（按10%递增测试）
    for split_ratio in range(10, 100, 10):
        bonus1 = total_bonus * split_ratio / 100
        bonus2 = total_bonus - bonus1
        
        # 第一部分单独计税
        part1 = calculate_bonus_separate(bonus1)
        
        # 第二部分合并计税
        part2 = calculate_bonus_combined(
            bonus2, monthly_salary, social_insurance, special_deduction
        )
        
        total_split_tax = part1.tax + part2.tax
        
        if total_split_tax < min_tax:
            min_tax = total_split_tax
            optimal_split = [
                {"amount": bonus1, "method": "单独计税", "tax": part1.tax},
                {"amount": bonus2, "method": "合并计税", "tax": part2.tax},
            ]
        
        max_tax = max(max_tax, total_split_tax)
    
    return BonusOptimizationResult(
        total_bonus=total_bonus,
        optimal_split=optimal_split,
        total_tax=min_tax,
        worst_tax=max_tax,
        savings=max_tax - min_tax,
    )


# ==================== 跳槽薪资谈判 ====================

def calculate_salary_negotiation(
    target_net: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
) -> Dict:
    """
    跳槽薪资谈判助手 - 从税后反推税前

    Args:
        target_net: 目标税后收入
        social_insurance: 五险一金
        special_deduction: 专项附加扣除

    Returns:
        Dict: 谈判建议
    """
    gross = reverse_gross_from_net(target_net, social_insurance, special_deduction)
    
    result = calculate_monthly_tax(
        monthly_salary=gross,
        social_insurance=social_insurance,
        special_deduction=special_deduction,
    )
    
    # 建议的谈判范围（税前 ± 5%）
    gross_min = gross * 0.95
    gross_max = gross * 1.05
    
    result_min = calculate_monthly_tax(
        monthly_salary=gross_min,
        social_insurance=social_insurance,
        special_deduction=special_deduction,
    )
    
    result_max = calculate_monthly_tax(
        monthly_salary=gross_max,
        social_insurance=social_insurance,
        special_deduction=special_deduction,
    )
    
    return {
        "目标税后": target_net,
        "需要税前": gross,
        "五险一金": social_insurance,
        "个税": result.monthly_tax,
        "税率": f"{result.tax_rate*100:.0f}%",
        "谈判范围": {
            "最低": {
                "税前": gross_min,
                "税后": result_min.net_income,
            },
            "最高": {
                "税前": gross_max,
                "税后": result_max.net_income,
            },
        },
        "建议话术": f"考虑到税后到手{target_net:.0f}元，建议谈{gross:.0f}元的税前薪资",
    }


def compare_job_offers(
    offers: List[Dict],
    special_deduction: SpecialDeduction = None,
) -> Dict:
    """
    对比多个 Offer

    Args:
        offers: Offer 列表，每个包含 {name, salary, social_insurance, bonus}
        special_deduction: 专项附加扣除

    Returns:
        Dict: 对比结果
    """
    if special_deduction is None:
        special_deduction = SpecialDeduction()
    
    results = []
    
    for offer in offers:
        name = offer.get('name', 'Offer')
        salary = offer.get('salary', 0)
        social = offer.get('social_insurance', 0)
        bonus = offer.get('bonus', 0)
        
        # 计算月度个税
        monthly = calculate_monthly_tax(
            monthly_salary=salary,
            social_insurance=social,
            special_deduction=special_deduction,
        )
        
        # 计算年度个税
        annual = calculate_annual_tax(
            monthly_salary=salary,
            social_insurance=social,
            special_deduction=special_deduction,
        )
        
        # 计算年终奖（默认单独计税）
        bonus_result = None
        if bonus > 0:
            bonus_result = calculate_bonus_separate(bonus)
        
        # 年度总到手
        annual_net = annual[-1].cumulative_tax
        total_annual_gross = salary * 12 + bonus
        total_annual_net = salary * 12 - social * 12 - annual_net
        if bonus_result:
            total_annual_net += bonus_result.net_bonus
        
        results.append({
            "名称": name,
            "月薪": salary,
            "五险一金": social,
            "月个税": monthly.monthly_tax,
            "月到手": monthly.net_income,
            "年终奖": bonus,
            "年终奖个税": bonus_result.tax if bonus_result else 0,
            "年终奖到手": bonus_result.net_bonus if bonus_result else 0,
            "年度总收入": total_annual_gross,
            "年度总到手": total_annual_net,
            "年度总个税": annual_net + (bonus_result.tax if bonus_result else 0),
        })
    
    # 按年度总到手排序
    sorted_results = sorted(results, key=lambda x: x['年度总到手'], reverse=True)
    
    # 添加排名
    for i, r in enumerate(sorted_results):
        r['排名'] = i + 1
    
    return {
        "对比结果": sorted_results,
        "推荐选择": sorted_results[0]['名称'] if sorted_results else None,
        "年度到手差额": sorted_results[0]['年度总到手'] - sorted_results[-1]['年度总到手'] if len(sorted_results) > 1 else 0,
    }


# ==================== 报告生成 ====================

def generate_tax_report(
    monthly_salary: float,
    social_insurance: float,
    special_deduction: SpecialDeduction,
    bonus: float = 0,
) -> str:
    """
    生成个税计算报告

    Args:
        monthly_salary: 月工资
        social_insurance: 五险一金
        special_deduction: 专项附加扣除
        bonus: 年终奖（可选）

    Returns:
        str: Markdown 格式的报告
    """
    # 计算年度个税
    annual_results = calculate_annual_tax(
        monthly_salary, social_insurance, special_deduction
    )

    # 统计
    annual_gross = monthly_salary * 12
    annual_social = social_insurance * 12
    annual_deduction = special_deduction.total_monthly * 12
    annual_tax = annual_results[-1].cumulative_tax
    annual_net = annual_gross - annual_social - annual_tax

    # 报告
    report = f"""# 📊 个税计算报告

## 基本信息

| 项目 | 月度 | 年度 |
|------|------|------|
| 税前收入 | ¥{monthly_salary:,.2f} | ¥{annual_gross:,.2f} |
| 五险一金 | ¥{social_insurance:,.2f} | ¥{annual_social:,.2f} |
| 专项附加扣除 | ¥{special_deduction.total_monthly:,.2f} | ¥{annual_deduction:,.2f} |
| 应纳税额 | - | ¥{annual_results[-1].taxable_income:,.2f} |
| 个税 | ¥{annual_tax/12:,.2f} | ¥{annual_tax:,.2f} |
| **税后收入** | **¥{annual_net/12:,.2f}** | **¥{annual_net:,.2f}** |

## 专项附加扣除明细

| 扣除项 | 金额（月） |
|--------|-----------|
| 子女教育 | ¥{special_deduction.children_education:,.2f} |
| 婴幼儿照护 | ¥{special_deduction.infant_care:,.2f} |
| 继续教育 | ¥{special_deduction.continuing_education:,.2f} |
| 住房贷款利息 | ¥{special_deduction.housing_loan:,.2f} |
| 住房租金 | ¥{special_deduction.housing_rent:,.2f} |
| 赡养老人 | ¥{special_deduction.elderly_support:,.2f} |
| **合计** | **¥{special_deduction.total_monthly:,.2f}** |

## 月度个税明细

| 月份 | 税前 | 五险一金 | 累计应税 | 税率 | 本月个税 | 累计个税 | 到手 |
|------|------|----------|----------|------|----------|----------|------|
"""

    for r in annual_results:
        report += f"| {r.month} | ¥{r.gross_income:,.0f} | ¥{r.social_insurance:,.0f} | ¥{r.taxable_income:,.0f} | {r.tax_rate*100:.0f}% | ¥{r.monthly_tax:,.0f} | ¥{r.cumulative_tax:,.0f} | ¥{r.net_income:,.0f} |\n"

    # 年终奖对比
    if bonus > 0:
        comparison = compare_bonus_methods(
            bonus, monthly_salary, social_insurance, special_deduction
        )

        report += f"""
## 年终奖计税对比（¥{bonus:,.0f}）

| 计税方式 | 月均额 | 税率 | 应纳税额 | 税后年终奖 |
|----------|--------|------|----------|-----------|
| 单独计税 | ¥{comparison['separate'].monthly_average:,.0f} | {comparison['separate'].tax_rate*100:.0f}% | ¥{comparison['separate'].tax:,.0f} | ¥{comparison['separate'].net_bonus:,.0f} |
| 合并计税 | - | {comparison['combined'].tax_rate*100:.0f}% | ¥{comparison['combined'].tax:,.0f} | ¥{comparison['combined'].net_bonus:,.0f} |

**推荐**：{'单独计税' if comparison['recommendation'] == 'separate' else '合并计税'}，可节省 ¥{comparison['savings']:,.0f}
"""

    report += f"""
---
*报告生成时间：2025年*
*税率依据：《个人所得税法》（2025年版）*
"""

    return report


# ==================== 快捷函数 ====================

def quick_calc(
    salary: float,
    social: float = 0,
    children: int = 0,
    infants: int = 0,
    education: bool = False,
    loan: bool = False,
    rent: int = 0,
    elderly: int = 0,
) -> Dict:
    """
    快速计算个税（简化版）

    Args:
        salary: 月工资
        social: 五险一金
        children: 子女数量（每人2000）
        infants: 婴幼儿数量（每人2000）
        education: 是否继续教育
        loan: 是否有房贷
        rent: 租房金额
        elderly: 赡养老人扣除额

    Returns:
        Dict: 计算结果
    """
    deduction = SpecialDeduction(
        children_education=children * 2000,
        infant_care=infants * 2000,
        continuing_education=400 if education else 0,
        housing_loan=1000 if loan else 0,
        housing_rent=rent,
        elderly_support=elderly,
    )

    result = calculate_monthly_tax(
        monthly_salary=salary,
        social_insurance=social,
        special_deduction=deduction,
    )

    return {
        "税前": salary,
        "五险一金": social,
        "专项扣除": deduction.total_monthly,
        "个税": result.monthly_tax,
        "到手": result.net_income,
        "税率": f"{result.tax_rate*100:.0f}%",
    }


if __name__ == "__main__":
    # 测试用例
    print("=" * 60)
    print("中国个税计算器测试 v1.1.0")
    print("=" * 60)

    # 测试1：月度个税
    deduction = SpecialDeduction(
        children_education=2000,
        housing_loan=1000,
        elderly_support=1000,
    )

    result = quick_calc(
        salary=30000,
        social=4500,
        children=1,
        loan=True,
        elderly=1000,
    )

    print("\n测试1：月度个税计算")
    for k, v in result.items():
        print(f"  {k}: {v}")

    # 测试2：年终奖对比
    print("\n测试2：年终奖计税对比")
    comparison = compare_bonus_methods(
        bonus=60000,
        monthly_salary=20000,
        social_insurance=3000,
        special_deduction=deduction,
    )

    print(f"  单独计税: ¥{comparison['separate'].tax:,.0f} (税后 ¥{comparison['separate'].net_bonus:,.0f})")
    print(f"  合并计税: ¥{comparison['combined'].tax:,.0f} (税后 ¥{comparison['combined'].net_bonus:,.0f})")
    print(f"  推荐: {comparison['recommendation']}, 节省 ¥{comparison['savings']:,.0f}")

    # 测试3：反推税前
    print("\n测试3：反推税前工资")
    gross = reverse_gross_from_net(
        target_net=25000,
        social_insurance=4000,
        special_deduction=deduction,
    )
    print(f"  目标到手: ¥25,000")
    print(f"  需要税前: ¥{gross:,.2f}")
    
    # 测试4：年度汇算清缴
    print("\n测试4：年度汇算清缴")
    income = IncomeSource(
        salary=360000,  # 年薪30k*12
        labor_income=20000,  # 劳务报酬
        royalty_income=10000,  # 稿酬
    )
    settlement = calculate_annual_settlement(
        income_sources=income,
        annual_social_insurance=54000,  # 4500*12
        special_deduction=deduction,
        prepaid_tax=25000,  # 已预缴
    )
    print(f"  综合所得: ¥{settlement.comprehensive_income:,.0f}")
    print(f"  应纳税额: ¥{settlement.annual_tax:,.0f}")
    print(f"  已预缴: ¥{settlement.prepaid_tax:,.0f}")
    print(f"  {settlement.status_text}")
    
    # 测试5：年终奖优化
    print("\n测试5：年终奖智能优化")
    optimization = optimize_bonus_allocation(
        total_bonus=100000,
        monthly_salary=20000,
        social_insurance=3000,
        special_deduction=deduction,
    )
    print(f"  年终奖总额: ¥{optimization.total_bonus:,.0f}")
    print(f"  最优方案总税额: ¥{optimization.total_tax:,.0f}")
    print(f"  最差方案总税额: ¥{optimization.worst_tax:,.0f}")
    print(f"  节省: ¥{optimization.savings:,.0f}")
    print(f"  最优分配:")
    for split in optimization.optimal_split:
        print(f"    - ¥{split['amount']:,.0f} ({split['method']}, 税额 ¥{split['tax']:,.0f})")
    
    # 测试6：跳槽薪资谈判
    print("\n测试6：跳槽薪资谈判")
    negotiation = calculate_salary_negotiation(
        target_net=25000,
        social_insurance=4000,
        special_deduction=deduction,
    )
    print(f"  目标税后: ¥{negotiation['目标税后']:,.0f}")
    print(f"  需要税前: ¥{negotiation['需要税前']:,.0f}")
    print(f"  {negotiation['建议话术']}")
    
    # 测试7：Offer对比
    print("\n测试7：Offer对比")
    offers = [
        {"name": "A公司", "salary": 25000, "social_insurance": 4000, "bonus": 50000},
        {"name": "B公司", "salary": 28000, "social_insurance": 4500, "bonus": 30000},
        {"name": "C公司", "salary": 22000, "social_insurance": 3500, "bonus": 80000},
    ]
    comparison = compare_job_offers(offers, deduction)
    print(f"  推荐选择: {comparison['推荐选择']}")
    print(f"  年度到手差额: ¥{comparison['年度到手差额']:,.0f}")
    print("\n  各Offer详情:")
    for r in comparison['对比结果']:
        print(f"    {r['排名']}. {r['名称']}: 月薪¥{r['月薪']:,.0f}, 年度到手¥{r['年度总到手']:,.0f}")
    
    print("\n" + "=" * 60)
    print("所有测试完成！")
    print("=" * 60)
