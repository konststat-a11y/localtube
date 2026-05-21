document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }

  const submitter = event.submitter;
  if (submitter instanceof HTMLButtonElement) {
    submitter.disabled = true;
    submitter.dataset.originalText = submitter.textContent || "";
    submitter.textContent = "Подождите...";
  }
});
