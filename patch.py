with open("downloader.py", "r") as f:
    content = f.read()

import re
# We just need to remove the conflict markers and duplicate definitions
new_content = content.replace('''        torrent_words = [(t, set(normalize_title(t.name))) for t in torrents]

        # Precompute torrent words to avoid redundant string parsing (O(N*M) -> O(N+M))
        precomputed_torrents = [(t, set(normalize_title(t.name))) for t in torrents]

        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))

<<<<<<< Updated upstream
            for t, t_words in torrent_words:
=======
            for t, t_words in precomputed_torrents:
>>>>>>> Stashed changes''', '''        # Precompute torrent words to avoid redundant string parsing (O(N*M) -> O(N+M))
        precomputed_torrents = [(t, set(normalize_title(t.name))) for t in torrents]

        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))

            for t, t_words in precomputed_torrents:''')

with open("downloader.py", "w") as f:
    f.write(new_content)
