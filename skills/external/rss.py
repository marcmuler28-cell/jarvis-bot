import feedparser
from typing import List, Dict
from datetime import datetime, timezone

# Feeds configurables (puedes añadir más)
FEEDS = [
    ("El Comercio", "https://elcomercio.pe/feed/portada.xml"),
    ("RPP", "https://rpp.pe/rss/ultimas"),
    ("Gestión", "https://gestion.pe/feed/tecnologia.xml"),
    # Añade aquí tus favoritos (BBC Mundo, CNN, etc.)
]

class RSSReader:
    def __init__(self, feeds=FEEDS, max_items_per_feed=3):
        self.feeds = feeds
        self.max_items = max_items_per_feed

    def fetch_headlines(self) -> List[Dict]:
        """Devuelve lista de titulares recientes con fuente, título y enlace."""
        headlines = []
        for source, url in self.feeds:
            try:
                feed = feedparser.parse(url)
                # Solo tomamos entradas de las últimas 24 horas
                now = datetime.now(timezone.utc)
                count = 0
                for entry in feed.entries:
                    if hasattr(entry, 'published_parsed') and entry.published_parsed:
                        pub_time = datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
                        if (now - pub_time).total_seconds() > 86400:
                            continue  # Más de 24h, ignorar
                    headlines.append({
                        "source": source,
                        "title": entry.title.strip() if hasattr(entry, 'title') else "",
                        "link": entry.link if hasattr(entry, 'link') else "",
                    })
                    count += 1
                    if count >= self.max_items:
                        break
            except Exception as e:
                headlines.append({
                    "source": source,
                    "title": f"[Error al cargar: {e}]",
                    "link": "",
                })
        return headlines

    def headlines_text(self) -> str:
        """Formatea los titulares como texto para el prompt."""
        items = self.fetch_headlines()
        if not items:
            return "No se encontraron noticias recientes."
        lines = []
        for item in items:
            lines.append(f"{item['source']}: {item['title']}")
        return "\n".join(lines)