"""
Output formatters for content planning results.
Supports JSON, Google Sheets, Email, and Slack/Discord formats.
"""
import json
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class ContentOutputFormatter:
    """Formats content planning results for various output destinations."""

    @staticmethod
    def to_json(data: Dict, output_path: Optional[str] = None) -> str:
        """
        Format results as JSON.

        Args:
            data: Content planning results dictionary
            output_path: Optional path to save JSON file

        Returns:
            JSON string
        """
        json_str = json.dumps(data, indent=2, ensure_ascii=False)
        
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(json_str)
            logger.info(f"Saved JSON output to {output_path}")
        
        return json_str

    @staticmethod
    def to_email_text(data: Dict) -> str:
        """
        Format results as plain text email.

        Args:
            data: Content planning results dictionary

        Returns:
            Formatted email text
        """
        lines = []
        lines.append("=" * 60)
        lines.append("WEEKLY CONTENT PLAN - IntelliVerse Health")
        lines.append("=" * 60)
        lines.append(f"Generated: {data.get('generatedAt', 'N/A')}")
        lines.append("")
        
        # Top Clusters
        lines.append("TOP 10 TREND CLUSTERS:")
        lines.append("-" * 60)
        for i, cluster in enumerate(data.get('topClusters', [])[:10], 1):
            lines.append(f"{i}. {cluster.get('displayTitle', cluster.get('topic', 'N/A'))}")
            lines.append(f"   Score: {cluster.get('score', 0):.1f} | Sources: {', '.join(cluster.get('sources', []))}")
            lines.append(f"   Velocity: {cluster.get('velocity', 'N/A')}")
            lines.append("")
        
        # Long-form
        lines.append("")
        lines.append("LONG-FORM TOPICS (2):")
        lines.append("-" * 60)
        for i, long_topic in enumerate(data.get('longForm', []), 1):
            lines.append(f"{i}. {long_topic.get('title', 'N/A')}")
            lines.append(f"   Why: {long_topic.get('why', 'N/A')}")
            lines.append("")
        
        # Calendar
        lines.append("")
        lines.append("7-DAY CONTENT CALENDAR:")
        lines.append("-" * 60)
        for day_data in data.get('calendar7Days', []):
            lines.append(f"\n{day_data.get('day', 'N/A')}:")
            for j, short in enumerate(day_data.get('shorts', []), 1):
                lines.append(f"  Short {j}: {short.get('hook', 'N/A')}")
                lines.append(f"    Angle: {short.get('angle', 'N/A')}")
                lines.append(f"    Pillar: {short.get('pillar', 'N/A')}")
        
        lines.append("")
        lines.append("=" * 60)
        
        return "\n".join(lines)

    @staticmethod
    def to_slack_message(data: Dict) -> Dict:
        """
        Format results as Slack message blocks.

        Args:
            data: Content planning results dictionary

        Returns:
            Slack message blocks dictionary
        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "📅 Weekly Content Plan - IntelliVerse Health"
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Generated:* {data.get('generatedAt', 'N/A')}"
                }
            },
            {
                "type": "divider"
            }
        ]
        
        # Top Clusters
        clusters_text = "*Top 10 Trend Clusters:*\n"
        for i, cluster in enumerate(data.get('topClusters', [])[:10], 1):
            clusters_text += f"{i}. *{cluster.get('displayTitle', cluster.get('topic', 'N/A'))}*\n"
            clusters_text += f"   Score: {cluster.get('score', 0):.1f} | {', '.join(cluster.get('sources', []))}\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": clusters_text
            }
        })
        
        blocks.append({"type": "divider"})
        
        # Long-form
        long_text = "*Long-Form Topics:*\n"
        for i, long_topic in enumerate(data.get('longForm', []), 1):
            long_text += f"{i}. {long_topic.get('title', 'N/A')}\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": long_text
            }
        })
        
        blocks.append({"type": "divider"})
        
        # Calendar
        calendar_text = "*7-Day Calendar:*\n"
        for day_data in data.get('calendar7Days', []):
            day_name = day_data.get('day', 'N/A')
            shorts = day_data.get('shorts', [])
            calendar_text += f"\n*{day_name}:*\n"
            for j, short in enumerate(shorts, 1):
                calendar_text += f"  • {short.get('hook', 'N/A')}\n"
        
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": calendar_text
            }
        })
        
        return {"blocks": blocks}

    @staticmethod
    def to_google_sheets_rows(data: Dict) -> List[List[str]]:
        """
        Format results as rows for Google Sheets.

        Args:
            data: Content planning results dictionary

        Returns:
            List of rows (each row is a list of strings)
        """
        rows = []
        
        # Header
        rows.append([
            "Week of",
            "Day",
            "Short 1 Hook",
            "Short 1 Angle",
            "Short 1 Pillar",
            "Short 2 Hook",
            "Short 2 Angle",
            "Short 2 Pillar",
            "Long-form Title",
            "Sources/Links"
        ])
        
        # Get week start date
        week_start = datetime.fromisoformat(data.get('generatedAt', datetime.now().isoformat())).strftime('%Y-%m-%d')
        
        # Calendar rows
        for day_data in data.get('calendar7Days', []):
            shorts = day_data.get('shorts', [])
            short1 = shorts[0] if len(shorts) > 0 else {}
            short2 = shorts[1] if len(shorts) > 1 else {}
            
            # Long-form (only for first day, or distribute as needed)
            long_title = ""
            long_links = ""
            if day_data.get('day') == 'Mon':
                long_topics = data.get('longForm', [])
                if long_topics:
                    long_title = long_topics[0].get('title', '')
                    long_links = ', '.join([url.get('url', '') for url in long_topics[0].get('links', [])[:2]])
            
            rows.append([
                week_start,
                day_data.get('day', ''),
                short1.get('hook', ''),
                short1.get('angle', ''),
                short1.get('pillar', ''),
                short2.get('hook', ''),
                short2.get('angle', ''),
                short2.get('pillar', ''),
                long_title,
                long_links
            ])
        
        return rows

    @staticmethod
    def to_markdown(data: Dict) -> str:
        """
        Format results as Markdown.

        Args:
            data: Content planning results dictionary

        Returns:
            Markdown formatted string
        """
        lines = []
        lines.append("# Weekly Content Plan - IntelliVerse Health")
        lines.append("")
        lines.append(f"**Generated:** {data.get('generatedAt', 'N/A')}")
        lines.append("")
        
        # Top Clusters
        lines.append("## Top 10 Trend Clusters")
        lines.append("")
        for i, cluster in enumerate(data.get('topClusters', [])[:10], 1):
            lines.append(f"### {i}. {cluster.get('displayTitle', cluster.get('topic', 'N/A'))}")
            lines.append(f"- **Score:** {cluster.get('score', 0):.1f}")
            lines.append(f"- **Sources:** {', '.join(cluster.get('sources', []))}")
            lines.append(f"- **Velocity:** {cluster.get('velocity', 'N/A')}")
            lines.append(f"- **Pillar:** {cluster.get('pillar', 'N/A')}")
            lines.append("")
            lines.append("**Links:**")
            for url_data in cluster.get('urls', [])[:3]:
                lines.append(f"- [{url_data.get('title', 'Link')}]({url_data.get('url', '')})")
            lines.append("")
        
        # Long-form
        lines.append("## Long-Form Topics")
        lines.append("")
        for i, long_topic in enumerate(data.get('longForm', []), 1):
            lines.append(f"### {i}. {long_topic.get('title', 'N/A')}")
            lines.append(f"- **Why:** {long_topic.get('why', 'N/A')}")
            lines.append(f"- **Pillar:** {long_topic.get('pillar', 'N/A')}")
            lines.append("")
            lines.append("**Links:**")
            for link in long_topic.get('links', []):
                lines.append(f"- [{link.get('title', 'Link')}]({link.get('url', '')})")
            lines.append("")
        
        # Calendar
        lines.append("## 7-Day Content Calendar")
        lines.append("")
        for day_data in data.get('calendar7Days', []):
            lines.append(f"### {day_data.get('day', 'N/A')}")
            for j, short in enumerate(day_data.get('shorts', []), 1):
                lines.append(f"**Short {j}:** {short.get('hook', 'N/A')}")
                lines.append(f"- Angle: {short.get('angle', 'N/A')}")
                lines.append(f"- Pillar: {short.get('pillar', 'N/A')}")
                lines.append("")
        
        return "\n".join(lines)
