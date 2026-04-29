document.addEventListener("DOMContentLoaded", () => {
    const animatedItems = document.querySelectorAll(
        ".brand-panel, .login-panel, .stat-card, .table-panel, .habit-card"
    );
    const habitInput = document.querySelector("#title");
    const suggestionButtons = document.querySelectorAll(".suggestion-chip");
    const calendarDays = document.querySelectorAll(".calendar-day:not(:disabled)");
    const detailDate = document.querySelector("#calendar-detail-date");
    const detailSummary = document.querySelector("#calendar-detail-summary");
    const detailList = document.querySelector("#calendar-detail-list");
    const reminderButton = document.querySelector("#enable-reminders");
    const reminderStatus = document.querySelector("#reminder-status");
    const reminderHabits = document.querySelectorAll(".habit-card[data-reminder-time]");

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

    const showCalendarDetails = (button) => {
        if (!detailDate || !detailSummary || !detailList) {
            return;
        }

        const tasks = (button.dataset.tasks || "")
            .split("||")
            .map((task) => task.trim())
            .filter(Boolean);
        const completed = button.dataset.completed || "0";
        const target = button.dataset.target || "0";

        calendarDays.forEach((day) => day.classList.remove("selected"));
        button.classList.add("selected");

        detailDate.textContent = button.dataset.date || "Selected day";
        detailSummary.textContent = `${completed} of ${target} habits completed`;
        detailList.innerHTML = "";

        if (tasks.length === 0) {
            const emptyItem = document.createElement("li");
            emptyItem.textContent = "No habits completed on this day.";
            detailList.append(emptyItem);
            return;
        }

        tasks.forEach((task) => {
            const item = document.createElement("li");
            item.textContent = task;
            detailList.append(item);
        });
    };

    calendarDays.forEach((button) => {
        button.addEventListener("click", () => showCalendarDetails(button));
    });

    const todayButton = document.querySelector(".calendar-day.today:not(:disabled)");
    if (todayButton) {
        showCalendarDetails(todayButton);
    }

    const setReminderStatus = (message) => {
        if (reminderStatus) {
            reminderStatus.textContent = message;
        }
    };

    const todayKey = () => new Date().toISOString().slice(0, 10);

    const sendDueReminders = () => {
        if (!("Notification" in window) || Notification.permission !== "granted") {
            return;
        }

        const now = new Date();
        const currentTime = `${String(now.getHours()).padStart(2, "0")}:${String(
            now.getMinutes()
        ).padStart(2, "0")}`;

        reminderHabits.forEach((habit) => {
            const reminderTime = habit.dataset.reminderTime;
            const isComplete = habit.dataset.completedToday === "1";

            if (!reminderTime || isComplete || reminderTime > currentTime) {
                return;
            }

            const habitId = habit.dataset.habitId;
            const reminderKey = `habitboost-reminder-${todayKey()}-${habitId}-${reminderTime}`;

            if (localStorage.getItem(reminderKey)) {
                return;
            }

            localStorage.setItem(reminderKey, "sent");
            new Notification("HabitBoost reminder", {
                body: `Time for: ${habit.dataset.habitTitle}`,
            });
        });
    };

    const startReminderChecks = () => {
        const scheduledCount = Array.from(reminderHabits).filter(
            (habit) => habit.dataset.reminderTime
        ).length;

        if (scheduledCount === 0) {
            setReminderStatus("No reminder times are set yet.");
            return;
        }

        setReminderStatus(`Notifications are on for ${scheduledCount} habit reminders.`);
        sendDueReminders();
        window.setInterval(sendDueReminders, 60000);
    };

    if (reminderButton && !("Notification" in window)) {
        reminderButton.disabled = true;
        setReminderStatus("This browser does not support notifications.");
    }

    if (reminderButton && "Notification" in window) {
        if (Notification.permission === "granted") {
            reminderButton.textContent = "Notifications Enabled";
            reminderButton.disabled = true;
            startReminderChecks();
        } else if (Notification.permission === "denied") {
            reminderButton.disabled = true;
            setReminderStatus("Notifications are blocked in this browser.");
        }

        reminderButton.addEventListener("click", async () => {
            const permission = await Notification.requestPermission();

            if (permission === "granted") {
                reminderButton.textContent = "Notifications Enabled";
                reminderButton.disabled = true;
                startReminderChecks();
                return;
            }

            setReminderStatus("Notifications were not enabled.");
        });
    }
});
