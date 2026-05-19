from __future__ import annotations

from typing import Any

# Static mapping of metrics for each rule-based insight key
INSIGHT_CONFIGS = {
    "low_runway": {
        "financial_risk": 1.0,
        "behavior_pattern": 0.3,
        "urgency": 1.0
    },
    "negative_savings": {
        "financial_risk": 0.8,
        "behavior_pattern": 0.7,
        "urgency": 0.7
    },
    "high_debt_stress": {
        "financial_risk": 0.9,
        "behavior_pattern": 0.5,
        "urgency": 0.6
    },
    "impulse_spending": {
        "financial_risk": 0.5,
        "behavior_pattern": 1.0,
        "urgency": 0.4
    }
}

def calculate_priority_score(insight_key: str, confidence: float) -> float:
    """
    Calculate priority score based on formula:
    priority_score = financial_risk * 0.4 + behavior_pattern * 0.3 + urgency * 0.2 + confidence * 0.1
    """
    config = INSIGHT_CONFIGS.get(insight_key, {
        "financial_risk": 0.5,
        "behavior_pattern": 0.5,
        "urgency": 0.5
    })
    
    risk = config["financial_risk"]
    behavior = config["behavior_pattern"]
    urgency = config["urgency"]
    
    score = (risk * 0.4) + (behavior * 0.3) + (urgency * 0.2) + (confidence * 0.1)
    return round(score, 3)

def select_top_insights(insights: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Given a list of active insights, calculates their priority scores and returns:
    - main_problem: The highest scoring insight (or None)
    - secondary_insight: The second highest scoring insight (or None)
    """
    scored_insights = []
    for ins in insights:
        key = ins.get("key") or ins.get("insight_key")
        conf = ins.get("confidence", 1.0)
        
        score = calculate_priority_score(key, conf)
        scored_insights.append({
            "key": key,
            "text": ins.get("text") or ins.get("insight_text"),
            "confidence": conf,
            "priority_score": score
        })
        
    # Sort descending by priority score
    scored_insights.sort(key=lambda x: x["priority_score"], reverse=True)
    
    main_problem = scored_insights[0] if len(scored_insights) > 0 else None
    secondary_insight = scored_insights[1] if len(scored_insights) > 1 else None
    
    return {
        "main_problem": main_problem,
        "secondary_insight": secondary_insight,
        "all_active_count": len(scored_insights)
    }
