// Problem page: editor, loading the solution from a file and submitting it.
"use strict";

(function () {
  const form = document.getElementById("submit-form");
  const button = document.getElementById("submit-button");
  const spinner = document.getElementById("submit-spinner");
  const feedback = document.getElementById("feedback");
  const view = HaskellEditor.create(document.getElementById("editor"), {
    doc: JSON.parse(document.getElementById("initial-code").textContent),
  });

  function showModal(id) {
    bootstrap.Modal.getOrCreateInstance(document.getElementById(id)).show();
  }

  function showError(message) {
    document.getElementById("error-message").textContent =
      message || document.getElementById("connection-error").textContent;
    showModal("error-window");
  }

  function setBusy(busy) {
    button.disabled = busy;
    spinner.hidden = !busy;
    HaskellEditor.setReadOnly(view, busy);
  }

  function showResult(data) {
    // The feedback is HTML rendered (and escaped) by the server
    feedback.innerHTML = data.feedback;
    HaskellEditor.showDiagnostics(view, data.diagnostics);
    if (data.verdict === "AC") {
      document.getElementById("check-icon").classList.remove("icon-hidden");
    }
    document.getElementById("result-title").textContent = data.title;
    document.getElementById("result-summary").textContent = data.summary;
    showModal("result-window");
  }

  const moreTestsButton = document.getElementById("more-tests-button");
  if (moreTestsButton) {
    moreTestsButton.addEventListener("click", () => {
      const moreTests = document.getElementById("more-tests");
      moreTests.hidden = !moreTests.hidden;
      moreTestsButton.setAttribute("aria-expanded", String(!moreTests.hidden));
      moreTestsButton.textContent = moreTests.hidden ? moreTestsButton.dataset.show : moreTestsButton.dataset.hide;
    });
  }

  document.getElementById("code-file").addEventListener("change", (event) => {
    const file = event.target.files[0];
    if (file) {
      file.text().then((text) => HaskellEditor.setCode(view, text));
    }
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    setBusy(true);
    const body = new FormData();
    body.append("code", HaskellEditor.getCode(view));
    try {
      const response = await fetch(form.dataset.endpoint, {
        method: "POST",
        credentials: "same-origin",
        headers: { "X-CSRFToken": form.querySelector("input[name=csrfmiddlewaretoken]").value },
        body,
      });
      const data = await response.json().catch(() => ({}));
      if (response.ok) {
        showResult(data);
      } else {
        showError(data.error);
      }
    } catch (error) {
      showError(null);
    } finally {
      setBusy(false);
    }
  });
})();
