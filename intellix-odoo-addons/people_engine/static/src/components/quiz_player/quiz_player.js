/** @odoo-module **/

import { Component, onMounted, onWillStart, onWillUnmount, useState } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

export class QuizPlayer extends Component {
    static template = "people_engine.QuizPlayer";
    static props = {
        quizId: { type: Number },
        employeeId: { type: Number },
        remainingAttempts: { type: Number, optional: true },
        canStart: { type: Boolean, optional: true },
        onComplete: { type: Function, optional: true },
    };

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");

        this.state = useState({
            phase: "loading",
            quiz: null,
            questions: [],
            currentIndex: 0,
            selectedAnswers: [],
            answeredCorrectly: null,
            explanation: "",
            attemptId: null,
            score: 0,
            totalCorrect: 0,
            passed: false,
            categoryScores: {},
            missedQuestions: [],
            remainingAttempts: this.props.remainingAttempts,
            canRetry: true,
            timeRemainingSec: 0,
        });

        this._timer = null;

        onWillStart(async () => {
            await this._loadQuiz();
        });

        onWillUnmount(() => {
            this._clearTimer();
        });
    }

    _clearTimer() {
        if (this._timer) {
            clearInterval(this._timer);
            this._timer = null;
        }
    }

    _startTimer(minutes) {
        this._clearTimer();
        if (!minutes || minutes <= 0) {
            return;
        }
        this.state.timeRemainingSec = minutes * 60;
        this._timer = setInterval(async () => {
            if (this.state.phase !== "question") {
                return;
            }
            this.state.timeRemainingSec -= 1;
            if (this.state.timeRemainingSec <= 0) {
                this._clearTimer();
                await this._finishQuiz(true);
            }
        }, 1000);
    }

    get timerLabel() {
        const sec = Math.max(this.state.timeRemainingSec, 0);
        const m = Math.floor(sec / 60);
        const s = sec % 60;
        return `${m}:${String(s).padStart(2, "0")}`;
    }

    async _loadQuiz() {
        const [quiz] = await this.orm.read("pe.quiz", [this.props.quizId], [
            "name",
            "description",
            "passing_score",
            "max_attempts",
            "time_limit",
            "randomize_questions",
            "show_correct_answers",
            "question_count",
            "croissance_points",
        ]);

        const questionIds = await this.orm.search(
            "pe.quiz.question",
            [["quiz_id", "=", this.props.quizId]],
            { order: "sequence, id" }
        );

        const questions = await this.orm.read("pe.quiz.question", questionIds, [
            "question_text",
            "question_type",
            "explanation",
            "category_tag",
            "points",
            "answer_ids",
        ]);

        for (const q of questions) {
            q.answers = await this.orm.read("pe.quiz.answer", q.answer_ids, [
                "answer_text",
                "is_correct",
                "sequence",
            ]);
            q.answers.sort((a, b) => a.sequence - b.sequence);
        }

        if (quiz.randomize_questions) {
            questions.sort(() => Math.random() - 0.5);
            for (const q of questions) {
                q.answers.sort(() => Math.random() - 0.5);
            }
        }

        const attemptId = await this.orm.create("pe.quiz.attempt", [
            {
                quiz_id: this.props.quizId,
                employee_id: this.props.employeeId,
            },
        ]);

        Object.assign(this.state, {
            quiz,
            questions,
            attemptId,
            phase: "intro",
            totalCorrect: 0,
            missedQuestions: [],
            categoryScores: {},
            canRetry:
                this.props.canStart !== false &&
                (this.props.remainingAttempts === undefined ||
                    this.props.remainingAttempts === null ||
                    this.props.remainingAttempts > 0),
        });
    }

    startQuiz() {
        this.state.phase = "question";
        this.state.currentIndex = 0;
        this._resetCurrentQuestion();
        this._startTimer(this.state.quiz.time_limit);
    }

    _resetCurrentQuestion() {
        this.state.selectedAnswers = [];
        this.state.answeredCorrectly = null;
        this.state.explanation = "";
    }

    toggleAnswer(answerId) {
        if (this.state.answeredCorrectly !== null) {
            return;
        }
        const q = this.state.questions[this.state.currentIndex];
        if (q.question_type === "single" || q.question_type === "true_false") {
            this.state.selectedAnswers = [answerId];
        } else {
            const idx = this.state.selectedAnswers.indexOf(answerId);
            if (idx >= 0) {
                this.state.selectedAnswers.splice(idx, 1);
            } else {
                this.state.selectedAnswers.push(answerId);
            }
        }
    }

    async validateAnswer() {
        if (!this.state.selectedAnswers.length) {
            return;
        }

        const q = this.state.questions[this.state.currentIndex];
        const correctIds = q.answers.filter((a) => a.is_correct).map((a) => a.id);
        const selected = new Set(this.state.selectedAnswers);
        const correct = new Set(correctIds);
        const isCorrect =
            selected.size === correct.size &&
            [...selected].every((id) => correct.has(id));

        this.state.answeredCorrectly = isCorrect;
        if (this.state.quiz.show_correct_answers) {
            this.state.explanation = q.explanation || "";
        }

        const cat = q.category_tag || "general";
        if (!this.state.categoryScores[cat]) {
            this.state.categoryScores[cat] = { correct: 0, total: 0 };
        }
        this.state.categoryScores[cat].total++;

        if (isCorrect) {
            this.state.totalCorrect++;
            this.state.categoryScores[cat].correct++;
        } else {
            const correctTexts = q.answers
                .filter((a) => a.is_correct)
                .map((a) => a.answer_text)
                .join(", ");
            this.state.missedQuestions.push({
                question: q.question_text,
                correctAnswer: correctTexts,
            });
        }

        await this.orm.create("pe.quiz.attempt.line", [
            {
                attempt_id: this.state.attemptId,
                question_id: q.id,
                selected_answer_ids: [[6, 0, this.state.selectedAnswers]],
                is_correct: isCorrect,
                points_earned: isCorrect ? q.points || 1 : 0,
            },
        ]);
    }

    async nextQuestion() {
        const total = this.state.questions.length;
        if (this.state.currentIndex < total - 1) {
            this.state.currentIndex++;
            this._resetCurrentQuestion();
        } else {
            await this._finishQuiz(false);
        }
    }

    async _finishQuiz(timedOut = false) {
        this._clearTimer();
        const total = this.state.questions.length;
        const correct = this.state.totalCorrect;

        let passed;
        if (timedOut) {
            passed = await this.orm.call(
                "pe.quiz.attempt",
                "action_complete_timeout",
                [this.state.attemptId, correct, total]
            );
        } else {
            passed = await this.orm.call(
                "pe.quiz.attempt",
                "action_complete",
                [[this.state.attemptId], correct, total]
            );
        }

        const scorePct = total ? Math.round((correct / total) * 100) : 0;
        this.state.score = scorePct;
        this.state.passed = passed;
        this.state.phase = "result";

        if (passed) {
            this.notification.add("Félicitations — certification obtenue !", {
                type: "success",
            });
        } else if (timedOut) {
            this.notification.add("Temps écoulé — tentative terminée.", {
                type: "warning",
            });
        }

        if (this.props.onComplete) {
            this.props.onComplete({
                passed,
                score: scorePct,
                attemptId: this.state.attemptId,
            });
        }

        if (
            this.state.quiz.max_attempts &&
            this.state.remainingAttempts !== undefined &&
            this.state.remainingAttempts !== null
        ) {
            this.state.remainingAttempts = Math.max(
                0,
                this.state.remainingAttempts - 1
            );
            this.state.canRetry = this.state.remainingAttempts > 0 && !passed;
        }
    }

    get currentQuestion() {
        return this.state.questions[this.state.currentIndex];
    }

    get progressPct() {
        if (!this.state.questions.length) {
            return 0;
        }
        return Math.round((this.state.currentIndex / this.state.questions.length) * 100);
    }

    get isLastQuestion() {
        return this.state.currentIndex === this.state.questions.length - 1;
    }

    get categoryEntries() {
        return Object.entries(this.state.categoryScores);
    }

    isSelected(answerId) {
        return this.state.selectedAnswers.includes(answerId);
    }

    getAnswerClass(answer) {
        if (this.state.answeredCorrectly === null) {
            return this.isSelected(answer.id) ? "pe-quiz-opt selected" : "pe-quiz-opt";
        }
        if (answer.is_correct) {
            return "pe-quiz-opt correct";
        }
        if (this.isSelected(answer.id) && !answer.is_correct) {
            return "pe-quiz-opt wrong";
        }
        return "pe-quiz-opt";
    }

    catPct(entry) {
        const [, stats] = entry;
        if (!stats.total) {
            return 0;
        }
        return Math.round((stats.correct / stats.total) * 100);
    }

    async restartQuiz() {
        if (!this.state.canRetry) {
            this.notification.add("Nombre maximum de tentatives atteint.", {
                type: "danger",
            });
            return;
        }
        this.state.phase = "loading";
        await this._loadQuiz();
    }
}

class PeQuizPlayerAction extends Component {
    static template = "people_engine.PeQuizPlayerAction";
    static components = { QuizPlayer };
    static props = ["*"];

    setup() {
        this.orm = useService("orm");
        this.notification = useService("notification");
        this.state = useState({
            loading: true,
            error: null,
            quizId: null,
            employeeId: null,
            remainingAttempts: null,
            canStart: true,
        });

        onWillStart(async () => {
            const quizId = this.props.action?.params?.quiz_id;
            if (!quizId) {
                this.state.error = "Quiz non spécifié.";
                this.state.loading = false;
                return;
            }
            try {
                const ctx = await this.orm.call("pe.quiz", "get_player_context", [
                    quizId,
                ]);
                this.state.quizId = ctx.quiz_id;
                this.state.employeeId = ctx.employee_id;
                this.state.remainingAttempts = ctx.remaining_attempts;
                this.state.canStart = ctx.can_start;
                if (!ctx.can_start) {
                    this.state.error =
                        "Nombre maximum de tentatives atteint pour ce quiz.";
                }
            } catch (err) {
                this.state.error = err?.message || "Impossible de charger le quiz.";
                this.notification.add(this.state.error, { type: "danger" });
            } finally {
                this.state.loading = false;
            }
        });
    }
}

registry.category("actions").add("pe_quiz_player", PeQuizPlayerAction);
