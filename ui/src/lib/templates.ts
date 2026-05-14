import type { FeedConfig } from "./types";

export type FeedTemplate = FeedConfig & {
  id: string;
  title: string;
  description: string;
  source_labels: string[];
};

export const feedTemplates: FeedTemplate[] = [
  {
    "id": "ai-ml-news",
    "title": "AI/ML news",
    "description": "Daily AI and machine-learning headlines from research and company blogs.",
    "source_labels": ["Hacker News", "ArXiv AI", "Anthropic", "OpenAI"],
    "name": "ai-ml-news",
    "schedule": "daily 09:00",
    "sources": [
      {"type": "rss", "name": "Hacker News", "url": "https://hnrss.org/frontpage"},
      {"type": "rss", "name": "ArXiv AI", "url": "https://arxiv.org/rss/cs.AI"},
      {"type": "rss", "name": "Anthropic", "url": "https://www.anthropic.com/news/rss.xml"},
      {"type": "rss", "name": "OpenAI", "url": "https://openai.com/news/rss.xml"}
    ],
    "pipeline": [
      "dedup",
      {"rank": {"min_relevance": 0.45}},
      "summarize",
      "digest"
    ],
    "render": {"max_items": 10}
  },
  {
    "id": "reddit-pulse",
    "title": "Reddit pulse",
    "description": "Hourly pulse of the top posts from r/MachineLearning.",
    "source_labels": ["r/MachineLearning"],
    "name": "reddit-pulse",
    "schedule": "every 1h",
    "sources": [
      {"type": "reddit", "subreddit": "MachineLearning", "sort": "top", "timeframe": "day", "limit": 10}
    ],
    "pipeline": [
      "dedup",
      {"rank": {"min_relevance": 0.35}},
      "summarize",
      "digest"
    ],
    "render": {"max_items": 5}
  },
  {
    "id": "web-search-briefing",
    "title": "Web search briefing",
    "description": "Daily SearXNG-powered news briefing for an editable topic.",
    "source_labels": ["SearXNG news search"],
    "name": "web-search-briefing",
    "schedule": "daily 08:00",
    "sources": [
      {"type": "search", "query": "AI infrastructure news", "engine": "searxng", "base_url": "http://searxng:8080", "categories": "news", "time_range": "day", "limit": 10}
    ],
    "pipeline": [
      "dedup",
      {"rank": {"min_relevance": 0.4}},
      "summarize",
      "digest"
    ],
    "render": {"max_items": 8}
  },
  {
    "id": "engineering-blogs",
    "title": "Engineering blogs",
    "description": "Weekly roundup from major software engineering blogs.",
    "source_labels": ["Cloudflare", "Stripe", "Netflix", "Discord", "Uber"],
    "name": "engineering-blogs",
    "schedule": "@weekly",
    "sources": [
      {"type": "rss", "name": "Cloudflare", "url": "https://blog.cloudflare.com/rss/"},
      {"type": "rss", "name": "Stripe", "url": "https://stripe.com/blog/feed.rss"},
      {"type": "rss", "name": "Netflix Tech", "url": "https://netflixtechblog.com/feed"},
      {"type": "rss", "name": "Discord", "url": "https://discord.com/blog/rss.xml"},
      {"type": "rss", "name": "Uber Engineering", "url": "https://www.uber.com/blog/engineering/rss/"}
    ],
    "pipeline": [
      "dedup",
      {"rank": {"min_relevance": 0.35}},
      "summarize",
      "digest"
    ],
    "render": {"max_items": 12}
  },
  {
    "id": "github-trending",
    "title": "GitHub trending",
    "description": "Weekly digest of repositories trending on GitHub.",
    "source_labels": ["github.com/trending"],
    "name": "github-trending",
    "schedule": "@weekly",
    "sources": [
      {"type": "scraper", "urls": ["https://github.com/trending"]}
    ],
    "pipeline": [
      "dedup",
      "summarize",
      "digest"
    ],
    "render": {"max_items": 10}
  },
  {
    "id": "custom-blank",
    "title": "Custom (start blank)",
    "description": "Open the feed editor and build a feed from scratch.",
    "source_labels": ["Blank feed editor"],
    "name": "custom-blank",
    "schedule": "daily 09:00",
    "sources": [
      {"type": "rss", "name": "Example RSS", "url": "https://example.com/feed.xml"}
    ],
    "pipeline": [
      "dedup"
    ],
    "render": {"max_items": 5}
  }
];

const metadataKeys = new Set(["id", "title", "description", "source_labels"]);

export function feedConfigFromTemplate(template: FeedTemplate): FeedConfig {
  return Object.fromEntries(
    Object.entries(template).filter(([key]) => !metadataKeys.has(key))
  ) as FeedConfig;
}
