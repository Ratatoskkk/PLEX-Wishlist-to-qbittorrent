with open("downloader.py", "r") as f:
    dl = f.read()

dl = dl.replace('''<<<<<<< HEAD
        # Precompute torrent words to avoid redundant string parsing (O(N*M) -> O(N+M))
        precomputed_torrents = [(t, set(normalize_title(t.name))) for t in torrents]

=======
        torrent_words = [(t, set(normalize_title(t.name))) for t in torrents]

>>>>>>> origin/main''', '''        # Precompute torrent words to avoid redundant string parsing (O(N*M) -> O(N+M))
        precomputed_torrents = [(t, set(normalize_title(t.name))) for t in torrents]
''')

dl = dl.replace('''<<<<<<< HEAD
            for t, t_words in precomputed_torrents:
=======
            for t, t_words in torrent_words:
>>>>>>> origin/main''', '''            for t, t_words in precomputed_torrents:''')

with open("downloader.py", "w") as f:
    f.write(dl)
