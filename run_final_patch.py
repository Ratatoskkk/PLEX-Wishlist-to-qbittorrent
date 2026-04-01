with open("downloader.py", "r") as f:
    dl = f.read()

dl = dl.replace('''        torrent_words = [(t, set(normalize_title(t.name))) for t in torrents]

        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))

            for t, t_words in torrent_words:''', '''        # Precompute torrent words to avoid redundant string parsing (O(N*M) -> O(N+M))
        precomputed_torrents = [(t, set(normalize_title(t.name))) for t in torrents]

        for item in active_db_items:
            db_id = item['id']
            plex_words = set(normalize_title(item['title']))

            for t, t_words in precomputed_torrents:''')

with open("downloader.py", "w") as f:
    f.write(dl)
