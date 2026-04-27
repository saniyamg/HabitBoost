document.addEventListener("DOMContentLoaded", () => {
    const animatedItems = document.querySelectorAll(
        ".brand-panel, .login-panel, .stat-card, .table-panel, .habit-card"
    );
    const habitInput = document.querySelector("#title");
    const suggestionButtons = document.querySelectorAll(".suggestion-chip");

    animatedItems.forEach((item, index) => {
        item.classList.add("reveal");
        item.style.animationDelay = `${index * 0.08}s`;
    });

    suggestionButtons.forEach((button) => {
        button.addEventListener("click", () => {
            if (!habitInput) {
                return;
            }

            habitInput.value = button.dataset.habit || "";
            habitInput.focus();
        });
    });
});
