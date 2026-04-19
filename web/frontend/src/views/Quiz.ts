/**
 * Quiz view — interactive Q&A for requirements gathering.
 */

export function renderQuiz(container: Element, navigate: (route: string) => void, projectId: string): void {
  container.innerHTML = `
    <header style="padding: 16px; border-bottom: 1px solid #333;">
      <button
        onclick="window._navigate('#projects')"
        style="background: none; border: none; color: #4fc3f7;
               font-size: 14px; cursor: pointer; padding: 8px 0;"
      >
        ← Back
      </button>
      <h1 style="font-size: 18px; margin-top: 8px;">Requirements Quiz</h1>
    </header>
    <main style="padding: 16px;">
      <div id="quiz-question" style="margin-bottom: 16px; font-size: 16px; line-height: 1.5;"></div>
      <div id="quiz-progress" style="color: #888; font-size: 14px; margin-bottom: 16px;"></div>
      <textarea
        id="quiz-answer"
        rows="3"
        placeholder="Type your answer..."
        style="width: 100%; padding: 12px; background: #16213e;
               border: 1px solid #333; border-radius: 8px;
               color: white; font-size: 16px; resize: vertical;"
      ></textarea>
      <button
        id="quiz-submit"
        class="tap-target"
        style="width: 100%; padding: 14px; margin-top: 12px;
               background: #0f3460; color: white; border: none;
               border-radius: 8px; font-size: 16px; cursor: pointer;"
      >
        Submit Answer
      </button>
      <div id="quiz-error" style="color: #e74c3c; margin-top: 12px; display: none;"></div>
      <div id="quiz-answers" style="margin-top: 24px;"></div>
    </main>
  `;

  const submitBtn = container.querySelector("#quiz-submit") as HTMLButtonElement;
  const errorEl = container.querySelector("#quiz-error") as HTMLDivElement;
  const answerInput = container.querySelector("#quiz-answer") as HTMLTextAreaElement;

  let answers: Array<{ question: string; answer: string }> = [];
  let currentQuestion = "";

  async function loadQuestion(): Promise<void> {
    try {
      const resp = await fetch(`/api/projects/${projectId}/quiz/next`);
      if (!resp.ok) throw new Error(`Failed to load question: ${resp.status}`);
      const data = await resp.json();

      if (data.done && data.qwendea) {
        showQwendeaPreview(data.qwendea);
        return;
      }

      currentQuestion = data.question || "";
      (container.querySelector("#quiz-question") as HTMLDivElement).textContent = currentQuestion;
      (container.querySelector("#quiz-progress") as HTMLDivElement).textContent =
        `Question ${answers.length + 1} of ${answers.length + 1}`;
    } catch (err: unknown) {
      errorEl.textContent = err instanceof Error ? err.message : "Failed to load question";
      errorEl.style.display = "block";
    }
  }

  function showQwendeaPreview(qwendea: string): void {
    container.querySelector("#quiz-question")!.innerHTML = `
      <h2 style="margin-bottom: 12px;">Synthesized Requirements</h2>
      <pre style="background: #16213e; padding: 16px; border-radius: 8px;
                  overflow-x: auto; font-size: 14px; white-space: pre-wrap;">${escapeHtml(qwendea)}</pre>
    `;
    (container.querySelector("#quiz-answer") as HTMLInputElement).style.display = "none";
    submitBtn.textContent = "Commit qwendea.md";
    submitBtn.onclick = async () => {
      navigate(`#project/${projectId}/artifacts/qwendea.md`);
    };
  }

  submitBtn.addEventListener("click", async () => {
    const answer = answerInput.value.trim();
    if (!answer) return;

    submitBtn.disabled = true;
    submitBtn.textContent = "Submitting...";

    try {
      const resp = await fetch(`/api/projects/${projectId}/quiz/answer`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ answer }),
      });

      if (!resp.ok) throw new Error(`Failed to submit: ${resp.status}`);
      const data = await resp.json();

      answers.push({ question: currentQuestion, answer });
      renderAnswer(answers.length - 1, answers[answers.length - 1]);

      if (data.done && data.qwendea) {
        showQwendeaPreview(data.qwendea);
      } else {
        currentQuestion = data.question || "";
        (container.querySelector("#quiz-question") as HTMLDivElement).textContent = currentQuestion;
        answerInput.value = "";
      }
    } catch (err: unknown) {
      errorEl.textContent = err instanceof Error ? err.message : "Failed to submit answer";
      errorEl.style.display = "block";
    } finally {
      submitBtn.disabled = false;
      submitBtn.textContent = "Submit Answer";
    }
  });

  loadQuestion();
}

function renderAnswer(index: number, qa: { question: string; answer: string }): void {
  const container = document.getElementById("quiz-answers");
  if (!container) return;

  const div = document.createElement("div");
  div.style.cssText = "margin-bottom: 12px; padding: 12px; background: #16213e; border-radius: 8px;";
  div.innerHTML = `
    <div style="font-size: 13px; color: #4fc3f7; margin-bottom: 4px;">Q${index + 1}: ${escapeHtml(qa.question)}</div>
    <div style="font-size: 14px;">${escapeHtml(qa.answer)}</div>
    <button class="edit-btn" data-index="${index}" style="margin-top: 8px; background: none;
      border: none; color: #888; font-size: 12px; cursor: pointer;">Edit</button>
  `;
  container.appendChild(div);

  div.querySelector(".edit-btn")?.addEventListener("click", () => {
    const turnIndex = parseInt(div.querySelector(".edit-btn")!.getAttribute("data-index")!, 10);
    const newAnswer = prompt("Edit answer:", qa.answer);
    if (newAnswer !== null && newAnswer.trim()) {
      editAnswer(turnIndex, newAnswer.trim());
    }
  });
}

async function editAnswer(turnIndex: number, answer: string): Promise<void> {
  try {
    const resp = await fetch(`/api/projects/${window._projectId}/quiz/edit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ turn: turnIndex, answer }),
    });
    if (!resp.ok) throw new Error(`Failed to edit: ${resp.status}`);
  } catch (err: unknown) {
    console.error("Edit failed:", err);
  }
}

function escapeHtml(text: string): string {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}
