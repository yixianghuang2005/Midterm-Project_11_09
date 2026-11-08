import os
import queue
import threading

import pygame
import requests

# Local test first. Replace this URL after Render deployment.
API_BASE_URL = os.environ.get(
    "WORDLE_API_URL", "http://127.0.0.1:8000"
).rstrip("/")

WIDTH, HEIGHT = 540, 820
BG = (18, 18, 19)
WHITE = (255, 255, 255)
OUTLINE = (58, 58, 60)
KEY_BG = (129, 131, 132)
COLORS = {
    "correct": (83, 141, 78),
    "present": (181, 159, 59),
    "absent": (58, 58, 60),
}
RANK = {"absent": 1, "present": 2, "correct": 3}


class WordleGame:
    def __init__(self):
        self.font = pygame.font.SysFont("Arial", 36, bold=True)
        ui_fonts = "microsoftjhenghei,msjh,simhei,simsun"
        self.small = pygame.font.SysFont(ui_fonts, 17)
        self.key_font = pygame.font.SysFont(ui_fonts, 19, bold=True)
        self.results = queue.Queue()
        self.restart_rect = pygame.Rect(365, 20, 150, 38)
        self.key_rects = []
        self.board_rect = pygame.Rect(110, 95, 320, 373)
        self.input_focused = True
        pygame.key.stop_text_input()
        self.busy = False
        self.game_id = None
        self.history = []
        self.current = ""
        self.key_states = {}
        self.game_over = False
        self.message = "正在連線伺服器，請稍候……"
        self.build_keyboard()
        self.start_new_game()

    def build_keyboard(self):
        rows = [list("QWERTYUIOP"), list("ASDFGHJKL"),
                ["ENTER"] + list("ZXCVBNM") + ["DEL"]]
        for row, keys in enumerate(rows):
            widths = [68 if len(key) > 1 else 44 for key in keys]
            x = (WIDTH - sum(widths) - 5 * (len(keys) - 1)) // 2
            for key, width in zip(keys, widths):
                rect = pygame.Rect(x, 560 + row * 61, width, 54)
                self.key_rects.append((rect, key))
                x += width + 5

    def request(self, kind, path, payload):
        if self.busy:
            return
        self.busy = True
        self.message = "正在連線，Render 免費服務可能需要約一分鐘喚醒。"

        def worker():
            try:
                response = requests.post(
                    API_BASE_URL + path, json=payload,
                    timeout=(10, 90),
                )
                data = response.json()
                if not response.ok:
                    detail = data.get("detail", "伺服器回應錯誤。")
                    raise ValueError(str(detail))
                self.results.put((kind, data, None))
            except (requests.RequestException, ValueError):
                # A lost response may still have consumed a server attempt.
                self.results.put((kind, None, "連線失敗。"))

        threading.Thread(target=worker, daemon=True).start()

    def start_new_game(self):
        self.request("new", "/api/new-game", {})

    def poll_results(self):
        try:
            kind, data, error = self.results.get_nowait()
        except queue.Empty:
            return
        self.busy = False
        if error:
            self.game_over = True
            self.message = "連線失敗，請檢查網址與後端，按 F2 重新開始。"
            return
        if kind == "new":
            self.game_id = data["game_id"]
            self.history = []
            self.current = ""
            self.key_states = {}
            self.game_over = False
            self.message = "請輸入五個英文字母，你有六次機會。"
            return
        self.history.append(data)
        for letter, state in zip(data["guess"], data["feedback"]):
            old = self.key_states.get(letter)
            if RANK[state] > RANK.get(old, 0):
                self.key_states[letter] = state
        self.current = ""
        self.game_over = data["status"] != "PLAYING"
        if data["status"] == "WON":
            self.message = f'恭喜答對！用了 {data["attempts"]}/6 次，按 F2 再玩一局。'
        elif data["status"] == "LOST":
            self.message = f'本局結束，答案是 {data["target_word"]}，按 F2 再玩一局。'
        else:
            self.message = f'還有 {6 - data["attempts"]} 次機會，請繼續猜。'

    def input_key(self, key):
        if self.busy:
            return
        if key == "F2":
            self.start_new_game()
            return
        if self.game_over or not self.game_id:
            return
        if key == "DEL":
            self.current = self.current[:-1]
        elif key == "ENTER":
            if len(self.current) != 5:
                self.message = "字母不足，請輸入五個英文字母再送出。"
                return
            self.request("guess", "/api/guess", {
                "game_id": self.game_id,
                "guess": self.current,
            })
        elif len(key) == 1 and key in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            if len(self.current) < 5:
                self.current += key

    def focus_input(self):
        # 本遊戲只收 A-Z 按鍵，停用輸入法組字以免吃掉 KEYDOWN。
        pygame.key.stop_text_input()
        self.input_focused = True

    def handle_event(self, event):
        if event.type == pygame.WINDOWFOCUSGAINED:
            self.focus_input()
        elif event.type == pygame.WINDOWFOCUSLOST:
            self.input_focused = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F2:
                self.input_key("F2")
            elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.input_key("ENTER")
            elif event.key in (pygame.K_BACKSPACE, pygame.K_DELETE):
                self.input_key("DEL")
            elif not getattr(event, "mod", 0) & (
                pygame.KMOD_CTRL | pygame.KMOD_ALT | pygame.KMOD_META
            ):
                # 直接處理 A-Z 按鍵，R 只輸入字母，不會重新開始。
                if pygame.K_a <= event.key <= pygame.K_z:
                    letter = chr(ord("A") + event.key - pygame.K_a)
                    self.input_key(letter)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.focus_input()
            if self.board_rect.collidepoint(event.pos):
                if not self.busy and not self.game_over and self.game_id:
                    self.message = "已選取本列，直接按 A-Z 輸入，Enter 送出。"
                return
            if self.restart_rect.collidepoint(event.pos):
                self.input_key("F2")
            else:
                for rect, key in self.key_rects:
                    if rect.collidepoint(event.pos):
                        self.input_key(key)
                        break

    @staticmethod
    def text_center(surface, font, text, center):
        label = font.render(text, True, WHITE)
        surface.blit(label, label.get_rect(center=center))

    def draw_message(self, surface):
        # 中文沒有空白分詞，因此逐字測量寬度後換行。
        lines, line = [], ""
        for char in self.message:
            trial = line + char
            if self.small.size(trial)[0] > WIDTH - 30 and line:
                lines.append(line)
                line = char
            else:
                line = trial
        lines.append(line)
        for i, line in enumerate(lines[:2]):
            self.text_center(surface, self.small, line,
                             (WIDTH // 2, 490 + 23 * i))

    def draw(self, surface):
        surface.fill(BG)
        surface.blit(self.font.render("WORDLE", True, WHITE), (25, 18))
        pygame.draw.line(surface, OUTLINE, (0, 75), (WIDTH, 75))
        button_color = OUTLINE if self.busy else (80, 82, 84)
        pygame.draw.rect(surface, button_color, self.restart_rect,
                         border_radius=5)
        self.text_center(surface, self.small, "重新開始 F2",
                         self.restart_rect.center)
        for row in range(6):
            result = self.history[row] if row < len(self.history) else None
            word = result["guess"] if result else (
                self.current if row == len(self.history) else ""
            )
            for col in range(5):
                rect = pygame.Rect(110 + col * 65, 95 + row * 63, 60, 58)
                state = result["feedback"][col] if result else None
                if state:
                    pygame.draw.rect(surface, COLORS[state], rect)
                else:
                    selected = (
                        row == len(self.history) and self.input_focused
                        and not self.busy and not self.game_over
                        and self.game_id is not None and col == len(self.current)
                    )
                    border = WHITE if selected else OUTLINE
                    pygame.draw.rect(surface, border, rect, width=2)
                if col < len(word):
                    self.text_center(surface, self.font, word[col], rect.center)
        self.draw_message(surface)
        for rect, key in self.key_rects:
            color = COLORS.get(self.key_states.get(key), KEY_BG)
            pygame.draw.rect(surface, color, rect, border_radius=4)
            label = {"ENTER": "送出", "DEL": "刪除"}.get(key, key)
            self.text_center(surface, self.key_font, label, rect.center)
        self.text_center(surface, self.small,
                         "實體鍵盤或滑鼠輸入｜Enter 送出｜退格刪除｜F2 重玩",
                         (WIDTH // 2, 765))
        self.text_center(surface, self.small,
                         "綠色：位置正確　黃色：位置不對　灰色：無可配對字母",
                         (WIDTH // 2, 794))


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.key.stop_text_input()
    pygame.display.set_caption("Wordle 猜字遊戲｜Pygame 與 FastAPI")
    clock = pygame.time.Clock()
    game = WordleGame()
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            else:
                game.handle_event(event)
        game.poll_results()
        game.draw(screen)
        pygame.display.flip()
        clock.tick(60)
    pygame.quit()


if __name__ == "__main__":
    main()
