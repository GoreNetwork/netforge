// Refresh any [data-poll] element from its partial until it reports it is done.
const POLL_MS = 2000;

document.querySelectorAll("[data-poll]").forEach((element) => {
  const timer = setInterval(async () => {
    try {
      const response = await fetch(element.dataset.poll);
      if (!response.ok) return;
      element.innerHTML = await response.text();
      if (element.querySelector("[data-poll-stop]")) clearInterval(timer);
    } catch {
      // Keep the last good content and try again on the next tick.
    }
  }, POLL_MS);
});
