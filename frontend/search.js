// Frontend client script for Private Search Engine
document.addEventListener("DOMContentLoaded", () => {
    const searchForm = document.getElementById("search-form");
    const queryInput = document.getElementById("query-input");
    const resultsContainer = document.getElementById("results");

    if (searchForm && queryInput && resultsContainer) {
        searchForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const query = queryInput.value.trim();
            if (!query) return;

            resultsContainer.innerHTML = "<p>Searching...</p>";

            try {
                const response = await fetch(`/api/search?q=${encodeURIComponent(query)}`);
                if (!response.ok) {
                    throw new Error(`Search request failed: ${response.status}`);
                }
                const data = await response.json();
                if (!data.results || data.results.length === 0) {
                    resultsContainer.innerHTML = "<p>No results found.</p>";
                    return;
                }
                resultsContainer.innerHTML = data.results.map((item) => `
                    <div class="result-card">
                        <a href="${item.url}" target="_blank" rel="noopener noreferrer">${item.title || item.url}</a>
                        <p class="snippet">${item.snippet || ""}</p>
                    </div>
                `).join("");
            } catch (err) {
                resultsContainer.innerHTML = `<p class="error">Error: ${err.message}</p>`;
            }
        });
    }
});

