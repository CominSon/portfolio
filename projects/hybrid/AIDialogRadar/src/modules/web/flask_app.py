import os

from flask import Flask, render_template, request, flash, redirect, url_for
from src.modules.core.dialog_orchestrator import DialogOrchestrator
from src.modules.sberchat.sberchat_manager import SberChatManager
from src.modules.web.web_config import WebConfig


class FlaskApp:
    def __init__(self, logger):
        self.logger = logger
        self.app = Flask(__name__, template_folder='templates', static_folder='static')
        self.app.secret_key = os.getenv('FLASK_SECRET_KEY')
        self.dialog_orchestrator = DialogOrchestrator(logger=self.logger)
        self.sberchat_manager: SberChatManager = SberChatManager(logger=self.logger)
        self._setup_routes()

    def _setup_routes(self):
        @self.app.route('/', methods=['GET', 'POST'])
        def index():
            attempts = None
            answer = None
            question = ""
            is_reference = None
            similarity = None
            ref_question = None
            if request.method == 'POST':
                question = request.form.get('question', '').strip()
                results = self.dialog_orchestrator.handle_question(question)
                attempts = 0  # Первый заход
                answer = results["answer"]
                is_reference = results["is_reference"]
                similarity = results["similarity"]
                ref_question = results["ref_question"]
            return render_template('index.html',
                                   question=question,
                                   answer=answer,
                                   is_reference=is_reference,
                                   similarity=similarity,
                                   ref_question=ref_question,
                                   attempts=attempts)

        @self.app.route("/like", methods=["POST"])
        def like():
            data = request.form
            result = self.dialog_orchestrator.handle_like(
                user_question=data["question"],
                answer=data["answer"],
                is_reference=data["is_reference"],
                similarity=data["similarity"],
                ref_question=data["ref_question"]
            )
            flash("👍 Лайк учтён" if result == "like_incremented" else "👍 Добавлен новый эталон")
            return redirect(url_for("index"))

        @self.app.route("/dislike", methods=["POST"])
        def dislike():
            data = request.form
            attempts = int(data.get("attempts", "0")) + 1
            if attempts >= 3:
                flash("К сожалению не получилось найти подходящий ответ.")
                return redirect(url_for("index"))
            results = self.dialog_orchestrator.handle_dislike(
                user_question=data["question"],
                is_reference=data.get("is_reference"),
                similarity=data["similarity"],
                ref_question=data.get("ref_question")
            )
            answer = results["answer"]
            is_reference = results["is_reference"]
            similarity = results["similarity"]
            ref_question = results["ref_question"]
            return render_template('index.html',
                                   question=data["question"],
                                   answer=answer,
                                   is_reference=is_reference,
                                   similarity=similarity,
                                   ref_question=ref_question,
                                   attempts=attempts
                                   )

        @self.app.route("/reload_chats", methods=["POST"])
        def reload_chats():
            try:
                self.sberchat_manager.safe_chat_in_base()
                flash("🔄 Чаты успешно обновлены")
            except Exception as e:
                flash(f"⚠️ Ошибка при обновлении чатов: {e}", "error")
            return redirect(url_for("index"))

    def run(self):
        """Запускаем Flask-приложение"""
        self.app.run(
            debug=WebConfig.DEBUG,
            host=WebConfig.HOST,
            port=WebConfig.PORT
        )
