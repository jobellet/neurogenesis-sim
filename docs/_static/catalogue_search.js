/**
 * Client-side search and category filtering for the Discovery Catalogue.
 */
document.addEventListener("DOMContentLoaded", () => {
  const searchInput = document.getElementById("catalogue-search");
  const filterPills = document.querySelectorAll(".catalogue-filter-pill");
  const cards = document.querySelectorAll(".catalogue-card");
  const counterEl = document.getElementById("catalogue-match-counter");

  if (!cards.length) return;

  let activeCategory = "all";
  let activeQuery = "";

  function updateFilter() {
    let visibleCount = 0;
    const query = activeQuery.toLowerCase().trim();

    cards.forEach((card) => {
      const category = card.getAttribute("data-category") || "";
      const text = (card.textContent || "").toLowerCase();

      const matchesCategory =
        activeCategory === "all" || category.toLowerCase() === activeCategory.toLowerCase();
      const matchesSearch = !query || text.includes(query);

      if (matchesCategory && matchesSearch) {
        card.style.display = "flex";
        visibleCount++;
      } else {
        card.style.display = "none";
      }
    });

    if (counterEl) {
      counterEl.textContent = `Showing ${visibleCount} of ${cards.length} circuits`;
    }
  }

  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      activeQuery = e.target.value;
      updateFilter();
    });
  }

  filterPills.forEach((pill) => {
    pill.addEventListener("click", () => {
      filterPills.forEach((p) => p.classList.remove("active"));
      pill.classList.add("active");
      activeCategory = pill.getAttribute("data-filter") || "all";
      updateFilter();
    });
  });

  // Copy loader code snippet on click
  document.querySelectorAll(".catalogue-copy-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const snippet = btn.getAttribute("data-snippet") || "";
      if (snippet) {
        navigator.clipboard.writeText(snippet).then(() => {
          const originalText = btn.textContent;
          btn.textContent = "Copied!";
          setTimeout(() => {
            btn.textContent = originalText;
          }, 1500);
        });
      }
    });
  });

  updateFilter();
});
