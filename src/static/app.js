document.addEventListener("DOMContentLoaded", () => {
  const activitiesList = document.getElementById("activities-list");
  const activitySelect = document.getElementById("activity");
  const signupForm = document.getElementById("signup-form");
  const messageDiv = document.getElementById("message");
  const authPanel = document.getElementById("auth-panel");
  const authForm = document.getElementById("auth-form");
  const authSubmit = document.getElementById("auth-submit");
  const accountStatus = document.getElementById("account-status");
  const logoutButton = document.getElementById("logout-button");
  const supervisorContainer = document.getElementById("supervisor-container");
  const assignmentForm = document.getElementById("assignment-form");
  const assignmentsList = document.getElementById("assignments-list");
  let currentUser = null;
  let authMode = "login";

  function showMessage(message, isError = false) {
    messageDiv.textContent = message;
    messageDiv.className = isError ? "error" : "success";
    setTimeout(() => messageDiv.classList.add("hidden"), 5000);
  }

  async function readResponse(response) {
    const result = await response.json();
    if (!response.ok) {
      throw new Error(result.detail || "An error occurred");
    }
    return result;
  }

  function setAuthMode(mode) {
    authMode = mode;
    authSubmit.textContent = mode === "login" ? "Sign In" : "Create Account";
    document.getElementById("auth-password").autocomplete =
      mode === "login" ? "current-password" : "new-password";
  }

  function renderAccount() {
    const signedIn = currentUser !== null;
    authPanel.classList.toggle("hidden", signedIn);
    logoutButton.classList.toggle("hidden", !signedIn);
    signupForm.classList.toggle(
      "hidden",
      !signedIn || currentUser.role !== "student"
    );
    if (!signedIn) {
      accountStatus.textContent =
        "Sign in or create a student account to manage your activity signups.";
      supervisorContainer.classList.add("hidden");
      return;
    }

    const roleNames = {
      student: "Student",
      club_admin: "Club administrator",
      supervisor: "Supervisor",
    };
    accountStatus.textContent = `${currentUser.email} · ${
      roleNames[currentUser.role]
    }${
      currentUser.clubs.length
        ? ` · Assigned clubs: ${currentUser.clubs.join(", ")}`
        : ""
    }`;
    supervisorContainer.classList.toggle(
      "hidden",
      currentUser.role !== "supervisor"
    );
    if (currentUser.role === "supervisor") {
      fetchAssignments();
    }
  }

  async function fetchCurrentUser() {
    try {
      const response = await fetch("/auth/me");
      currentUser = response.ok ? await response.json() : null;
    } catch (error) {
      currentUser = null;
      console.error("Error checking account:", error);
    }
    renderAccount();
  }

  function addParticipant(list, activityName, email) {
    const item = document.createElement("li");
    const participantEmail = document.createElement("span");
    participantEmail.className = "participant-email";
    participantEmail.textContent = email;
    item.appendChild(participantEmail);

    if (currentUser?.role === "student" && currentUser.email === email) {
      const unregisterButton = document.createElement("button");
      unregisterButton.className = "delete-btn";
      unregisterButton.type = "button";
      unregisterButton.textContent = "Unregister";
      unregisterButton.setAttribute(
        "aria-label",
        `Unregister from ${activityName}`
      );
      unregisterButton.addEventListener("click", () =>
        handleUnregister(activityName)
      );
      item.appendChild(unregisterButton);
    }
    list.appendChild(item);
  }

  async function fetchActivities() {
    try {
      const response = await fetch("/activities");
      const activities = await readResponse(response);
      activitiesList.replaceChildren();
      activitySelect.replaceChildren(new Option("-- Select an activity --", ""));

      Object.entries(activities).forEach(([name, details]) => {
        const activityCard = document.createElement("div");
        activityCard.className = "activity-card";

        const title = document.createElement("h4");
        title.textContent = name;
        activityCard.appendChild(title);

        const description = document.createElement("p");
        description.textContent = details.description;
        activityCard.appendChild(description);

        const schedule = document.createElement("p");
        const scheduleLabel = document.createElement("strong");
        scheduleLabel.textContent = "Schedule: ";
        schedule.append(scheduleLabel, details.schedule);
        activityCard.appendChild(schedule);

        const availability = document.createElement("p");
        availability.textContent = `Availability: ${
          details.max_participants - details.participants.length
        } spots left`;
        activityCard.appendChild(availability);

        const participantsContainer = document.createElement("div");
        participantsContainer.className = "participants-container";
        if (details.participants.length) {
          const heading = document.createElement("h5");
          heading.textContent = "Participants:";
          participantsContainer.appendChild(heading);
          const participantsList = document.createElement("ul");
          participantsList.className = "participants-list";
          details.participants.forEach((email) =>
            addParticipant(participantsList, name, email)
          );
          participantsContainer.appendChild(participantsList);
        } else {
          const emptyMessage = document.createElement("p");
          emptyMessage.textContent = "No participants yet";
          participantsContainer.appendChild(emptyMessage);
        }
        activityCard.appendChild(participantsContainer);
        activitiesList.appendChild(activityCard);
        activitySelect.add(new Option(name, name));
      });
    } catch (error) {
      activitiesList.textContent =
        "Failed to load activities. Please try again later.";
      console.error("Error fetching activities:", error);
    }
  }

  async function handleUnregister(activity) {
    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(activity)}/unregister`,
        { method: "DELETE" }
      );
      const result = await readResponse(response);
      showMessage(result.message);
      await fetchActivities();
    } catch (error) {
      showMessage(
        error.message || "Failed to unregister. Please try again.",
        true
      );
    }
  }

  document.getElementById("show-login").addEventListener("click", () => {
    setAuthMode("login");
  });
  document.getElementById("show-register").addEventListener("click", () => {
    setAuthMode("register");
  });

  authForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const credentials = {
      email: document.getElementById("auth-email").value,
      password: document.getElementById("auth-password").value,
    };
    try {
      const endpoint = authMode === "login" ? "login" : "register";
      const response = await fetch(`/auth/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(credentials),
      });
      const result = await readResponse(response);
      if (authMode === "register") {
        setAuthMode("login");
        document.getElementById("auth-password").value = "";
        showMessage(result.message);
        return;
      }
      authForm.reset();
      showMessage(result.message);
      await fetchCurrentUser();
      await fetchActivities();
    } catch (error) {
      showMessage(error.message || "Account request failed.", true);
    }
  });

  logoutButton.addEventListener("click", async () => {
    try {
      const response = await fetch("/auth/logout", { method: "POST" });
      const result = await readResponse(response);
      currentUser = null;
      renderAccount();
      await fetchActivities();
      showMessage(result.message);
    } catch (error) {
      showMessage(error.message || "Failed to sign out.", true);
    }
  });

  signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const activity = activitySelect.value;
    try {
      const response = await fetch(
        `/activities/${encodeURIComponent(activity)}/signup`,
        { method: "POST" }
      );
      const result = await readResponse(response);
      showMessage(result.message);
      await fetchActivities();
    } catch (error) {
      showMessage(error.message || "Failed to sign up. Please try again.", true);
    }
  });

  async function fetchAssignments() {
    try {
      const response = await fetch("/supervisor/club-assignments");
      const assignments = await readResponse(response);
      assignmentsList.replaceChildren();
      assignments.forEach(({ email, club_name }) => {
        const item = document.createElement("li");
        const assignmentText = document.createElement("span");
        assignmentText.textContent = `${club_name}: ${email}`;
        const removeButton = document.createElement("button");
        removeButton.className = "delete-btn";
        removeButton.type = "button";
        removeButton.textContent = "Remove";
        removeButton.addEventListener("click", () =>
          changeAssignment(email, club_name, "DELETE")
        );
        item.append(assignmentText, removeButton);
        assignmentsList.appendChild(item);
      });
    } catch (error) {
      showMessage(error.message || "Failed to load assignments.", true);
    }
  }

  async function changeAssignment(email, clubName, method) {
    try {
      const response = await fetch("/supervisor/club-assignments", {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, club_name: clubName }),
      });
      const result = await readResponse(response);
      showMessage(result.message);
      await fetchAssignments();
    } catch (error) {
      showMessage(error.message || "Failed to update assignment.", true);
    }
  }

  assignmentForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await changeAssignment(
      document.getElementById("administrator-email").value,
      document.getElementById("club-name").value,
      "PUT"
    );
    assignmentForm.reset();
  });

  setAuthMode("login");
  fetchCurrentUser().then(fetchActivities);
});
