import json
import os

class DataManager:
    def __init__(self, data_file, settings_file):
        self.data_file = data_file
        self.settings_file = settings_file
        
        # 개별 메모 파일을 저장할 디렉토리 설정 (예: memos_data)
        self.data_dir = os.path.join(os.path.dirname(data_file), "memos_data")
        if not os.path.exists(self.data_dir):
            os.makedirs(self.data_dir)

    def load_memos(self):
        """메모 데이터 로드 (개별 JSON 파일)"""
        memos = {}
        if os.path.exists(self.data_dir):
            for filename in os.listdir(self.data_dir):
                if filename.endswith(".json"):
                    try:
                        memo_id = os.path.splitext(filename)[0]
                        file_path = os.path.join(self.data_dir, filename)
                        with open(file_path, "r", encoding="utf-8") as f:
                            memos[memo_id] = json.load(f)
                    except Exception as e:
                        print(f"Error loading memo {filename}: {e}")
        
        # 2. 데이터가 없고 기존 단일 파일(memos.json)이 있다면 마이그레이션
        if not memos and os.path.exists(self.data_file):
            print("Migrating from single JSON to multiple files...")
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    old_memos = json.load(f)
                
                if old_memos:
                    self.save_memos(old_memos)
                    memos = old_memos
                    print(f"Migrated {len(memos)} memos.")
            except Exception as e:
                print(f"Migration failed: {e}")
                
        return memos

    def save_memos(self, memos):
        """메모 데이터 저장 (개별 JSON 파일)"""
        try:
            # 1. 현재 메모들 저장
            current_ids = set()
            for memo_id, data in memos.items():
                current_ids.add(memo_id)
                file_path = os.path.join(self.data_dir, f"{memo_id}.json")
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=4)
            
            # 2. 삭제된 메모 파일 정리
            if os.path.exists(self.data_dir):
                for filename in os.listdir(self.data_dir):
                    if filename.endswith(".json"):
                        file_id = os.path.splitext(filename)[0]
                        if file_id not in current_ids:
                            os.remove(os.path.join(self.data_dir, filename))
                            
        except Exception as e:
            print(f"Error saving data: {e}")

    def load_settings(self):
        """설정 데이터 로드"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading settings: {e}")
        return {}

    def save_settings(self, settings):
        """설정 데이터 저장"""
        try:
            with open(self.settings_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            print(f"Error saving settings: {e}")