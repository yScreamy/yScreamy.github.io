import datetime
import os

class Logger:
    @staticmethod
    def log(message):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{timestamp}] {message}"
        
        # Kiírás a konzolra
        print(formatted_message)
        
        # Mentés fájlba
        log_dir = "logs"
        if not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        with open(f"{log_dir}/bot_log.txt", "a", encoding="utf-8") as f:
            f.write(formatted_message + "\n")
