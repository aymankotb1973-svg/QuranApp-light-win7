import sqlite3
import os

class WordMeaningManager:
    def __init__(self, db_path):
        """
        Initializes the manager and connects to the SQLite database.
        """
        self.db_path = db_path
        self.conn = None
        self._connect()

    def _connect(self):
        """Connects to the SQLite database."""
        if not os.path.exists(self.db_path):
            print(f"Error: Database file not found at {self.db_path}")
            return
        try:
            self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
        except sqlite3.Error as e:
            print(f"Database connection error: {e}")
            self.conn = None

    def load_all_word_titles(self):
        """
        Loads all word titles from the database into a dictionary for fast lookup.
        Returns: dict {(sura_id, aya_id, word_id): title}
        """
        if not self.conn:
            return {}

        # Query based on the confirmed schema for 'project_contents' table
        query = """
            SELECT sura_id, aya_id, word_id, title
            FROM project_contents
            WHERE title IS NOT NULL AND title != ''
            ORDER BY word_id
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            
            # Create a dictionary mapping for O(1) access
            # Key: (sura, aya, word), Value: title
            titles_map = {}
            
            # Reconstruct local indices (sura, local_aya, local_word)
            last_sura = -1
            last_aya_id = -1
            local_aya = 0
            local_word = 0
            
            for row in rows:
                s_id = row['sura_id']
                a_id = row['aya_id']
                title = row['title']
                
                if s_id != last_sura: # New Surah
                    local_aya = 1; local_word = 1; last_sura = s_id; last_aya_id = a_id
                elif a_id != last_aya_id: # New Ayah
                    local_aya += 1; local_word = 1; last_aya_id = a_id
                else: # Same Ayah
                    local_word += 1
                
                # Key: (sura, local_aya, local_word) matching the renderer's expectation
                key = (s_id, local_aya, local_word)
                titles_map[key] = title
            
            print(f"Loaded {len(titles_map)} word titles from database (mapped to local indices).")
            return titles_map

        except sqlite3.Error as e:
            print(f"Query error loading word titles: {e}")
            return {}

    def load_id_mappings(self):
        """
        Builds mappings between Local IDs (Sura, LocalAya, LocalWord) and DB IDs (Global).
        Returns:
            local_to_global: {(sura, l_aya, l_word): global_word_id}
            global_to_db: {global_word_id: (sura_id, aya_id, word_id)}
            global_to_local: {global_word_id: (sura, l_aya, l_word)}
        """
        if not self.conn: return {}, {}, {}
        
        # Fetch all IDs ordered by global word_id (sequential 1..77432)
        query = "SELECT sura_id, aya_id, word_id FROM project_contents ORDER BY word_id"
        try:
            cursor = self.conn.cursor()
            cursor.execute(query)
            rows = cursor.fetchall()
            
            local_to_global = {}
            global_to_db = {}
            global_to_local = {}
            
            last_sura = -1
            last_aya_id = -1
            local_aya = 0
            local_word = 0
            
            for row in rows:
                s_id, a_id, w_id = row[0], row[1], row[2]
                
                if s_id != last_sura: # New Surah
                    local_aya = 1; local_word = 1; last_sura = s_id; last_aya_id = a_id
                elif a_id != last_aya_id: # New Ayah
                    local_aya += 1; local_word = 1; last_aya_id = a_id
                else: # Same Ayah
                    local_word += 1
                
                local_key = (s_id, local_aya, local_word)
                local_to_global[local_key] = w_id
                global_to_db[w_id] = (s_id, a_id, w_id)
                global_to_local[w_id] = local_key
                
            print(f"Loaded ID mappings for {len(global_to_db)} words.")
            return local_to_global, global_to_db, global_to_local
            
        except sqlite3.Error as e:
            print(f"Error loading ID mappings: {e}")
            return {}, {}, {}

    def __del__(self):
        """Closes the database connection when the object is destroyed."""
        if self.conn:
            self.conn.close()
