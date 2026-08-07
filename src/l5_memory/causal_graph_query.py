"""
L5 因果图谱查询
从 Neo4j 查询因果路径和关联事件，为决策提供因果依据。
"""

from __future__ import annotations

import logging
import os
from typing import Optional

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


class CausalGraphQuery:
    """
    Neo4j 因果图谱查询器。

    查询类型：
    - 单事件因果链：X 导致 Y 导致 Z
    - 多跳路径：A → B → C → 当前事件
    - 邻居事件：与当前行情相关的事件
    """

    def __init__(self, uri: str = "bolt://localhost:7687", user: str = "neo4j", password: str = ""):
        if not password:
            load_dotenv()
            password = os.environ.get("NEO4J_PASSWORD", "neo4j123")

        from neo4j import GraphDatabase
        self.driver = GraphDatabase.driver(uri, auth=(user, password))
        self.driver.verify_connectivity()
        logger.info("Neo4j connected")

    def ensure_schema(self):
        """确保因果图谱约束存在"""
        with self.driver.session() as s:
            s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE")
            s.run("CREATE CONSTRAINT IF NOT EXISTS FOR (f:Factor) REQUIRE f.name IS UNIQUE")
            s.run("CREATE INDEX IF NOT EXISTS FOR (e:Event) ON (e.type)")
        logger.info("Neo4j schema ensured")

    def write_causal_triplet(
        self,
        cause_name: str,
        cause_type: str,
        effect_name: str,
        effect_type: str,
        relation: str,
        confidence: float,
        evidence: str = "",
    ):
        """写入一条因果三元组到 Neo4j"""
        with self.driver.session() as s:
            s.run(
                """
                MERGE (c:Event {id: $cause_id})
                SET c.name = $cause_name, c.type = $cause_type
                MERGE (e:Event {id: $effect_id})
                SET e.name = $effect_name, e.type = $effect_type
                MERGE (c)-[r:CAUSES {relation: $rel}]->(e)
                SET r.confidence = $conf, r.evidence = $evidence, r.updated = datetime()
                """,
                cause_id=cause_name, cause_name=cause_name, cause_type=cause_type,
                effect_id=effect_name, effect_name=effect_name, effect_type=effect_type,
                rel=relation, conf=confidence, evidence=evidence,
            )

    def query_causal_paths(
        self, event_name: str, max_depth: int = 3, limit: int = 10
    ) -> list[dict]:
        """
        查询与指定事件相关的因果路径。

        Returns:
            [{cause, relation, effect, confidence, evidence}, ...]
        """
        with self.driver.session() as s:
            # 注意：Neo4j 不允许变长路径中使用 $param，直接拼接 depth
            query = f"""
                MATCH path = (c:Event)-[r:CAUSES*1..{max_depth}]->(e:Event)
                WHERE c.name CONTAINS $event OR e.name CONTAINS $event
                RETURN c.name as cause, e.name as effect,
                       [rel in relationships(path) | rel.relation] as relations,
                       [rel in relationships(path) | rel.confidence] as confidences,
                       [rel in relationships(path) | rel.evidence] as evidences,
                       length(path) as depth
                ORDER BY depth
                LIMIT $limit
            """
            result = s.run(query, event=event_name, limit=limit)
            records = []
            for r in result:
                records.append({
                    "cause": r["cause"],
                    "effect": r["effect"],
                    "relations": r["relations"],
                    "avg_confidence": sum(r["confidences"]) / len(r["confidences"]) if r["confidences"] else 0,
                    "depth": r["depth"],
                    "evidences": r["evidences"],
                })
            return records

    def query_related_events(
        self, keywords: list[str], limit: int = 10
    ) -> list[dict]:
        """根据关键词搜索相关因果事件"""
        with self.driver.session() as s:
            results = []
            for kw in keywords:
                r = s.run(
                    """
                    MATCH (e:Event)
                    WHERE e.name CONTAINS $kw
                    OPTIONAL MATCH (e)-[r:CAUSES]->(t:Event)
                    RETURN e.name as name, e.type as type,
                           collect(DISTINCT {rel: r.relation, conf: r.confidence, target: t.name}) as edges
                    LIMIT $limit
                    """,
                    kw=kw, limit=limit,
                )
                for row in r:
                    results.append({"name": row["name"], "type": row["type"], "edges": row["edges"]})
            return results

    def query_top_confidence_triplets(self, limit: int = 10) -> list[dict]:
        """查询置信度最高的因果三元组"""
        with self.driver.session() as s:
            r = s.run(
                """
                MATCH (c:Event)-[r:CAUSES]->(e:Event)
                WHERE r.confidence > 0.3
                RETURN c.name as cause, r.relation as relation, e.name as effect,
                       r.confidence as confidence, r.evidence as evidence
                ORDER BY r.confidence DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(record) for record in r]

    def clear(self):
        """清空图谱（仅测试用）"""
        with self.driver.session() as s:
            s.run("MATCH (n) DETACH DELETE n")

    def close(self):
        self.driver.close()
