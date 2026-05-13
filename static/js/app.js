(() => {
  const body = document.body;

  const savedTheme = localStorage.getItem("russian-market-theme");
  if (savedTheme === "dark") {
    body.classList.add("dark-theme");
  }

  document.addEventListener("click", async (event) => {
    const openButton = event.target.closest("[data-open-modal]");
    if (openButton) {
      const modal = document.getElementById(openButton.dataset.openModal);
      if (modal) {
        modal.classList.remove("is-hidden");
      }
      return;
    }

    const closeButton = event.target.closest("[data-close-modal]");
    if (closeButton) {
      const modal = document.getElementById(closeButton.dataset.closeModal);
      if (modal) {
        modal.classList.add("is-hidden");
      }
      return;
    }

    const modalBackdrop = event.target.classList.contains("modal-backdrop")
      ? event.target
      : null;
    if (modalBackdrop) {
      modalBackdrop.classList.add("is-hidden");
      return;
    }

    const themeButton = event.target.closest("[data-theme-toggle]");
    if (themeButton) {
      body.classList.toggle("dark-theme");
      localStorage.setItem(
        "russian-market-theme",
        body.classList.contains("dark-theme") ? "dark" : "light"
      );
      return;
    }

    const copyButton = event.target.closest("[data-copy]");
    if (copyButton) {
      const text = copyButton.dataset.copy;
      try {
        await navigator.clipboard.writeText(text);
        const previous = copyButton.textContent;
        copyButton.textContent = "Copied";
        setTimeout(() => {
          copyButton.textContent = previous;
        }, 1200);
      } catch (error) {
        copyButton.textContent = "Copy failed";
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") {
      return;
    }
    document.querySelectorAll(".modal-backdrop:not(.is-hidden)").forEach((modal) => {
      modal.classList.add("is-hidden");
    });
  });
})();
