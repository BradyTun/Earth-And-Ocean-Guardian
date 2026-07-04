const yearNode = document.getElementById("year");
const menuToggle = document.getElementById("menuToggle");
const mobileNav = document.getElementById("mobileNav");
const pageLoader = document.getElementById("pageLoader");

if (yearNode) {
    yearNode.textContent = String(new Date().getFullYear());
}

if (menuToggle && mobileNav) {
    menuToggle.addEventListener("click", () => {
        const expanded = menuToggle.getAttribute("aria-expanded") === "true";
        menuToggle.setAttribute("aria-expanded", String(!expanded));
        mobileNav.classList.toggle("hidden");
    });
}

function hideLoader() {
    if (!pageLoader) {
        return;
    }

    pageLoader.classList.add("is-hidden");
}

if (document.readyState === "complete") {
    window.setTimeout(hideLoader, 220);
} else {
    window.addEventListener("load", () => {
        window.setTimeout(hideLoader, 280);
    });
}

// If an animal photo fails to load, remove it so the emoji fallback shows.
document.querySelectorAll("img.js-animal-photo").forEach((img) => {
    const drop = () => img.remove();
    img.addEventListener("error", drop);
    if (img.complete && img.naturalWidth === 0) {
        drop();
    }
});

const revealElements = document.querySelectorAll("[data-reveal]");
if (revealElements.length > 0) {
    const observer = new IntersectionObserver(
        (entries, obs) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add("is-visible");
                    obs.unobserve(entry.target);
                }
            });
        },
        {
            threshold: 0.14,
            rootMargin: "0px 0px -36px 0px",
        }
    );

    revealElements.forEach((element, index) => {
        element.style.transitionDelay = `${Math.min(index * 80, 360)}ms`;
        observer.observe(element);
    });
}

function animateCounter(node) {
    const target = Number(node.dataset.count || "0");
    if (!Number.isFinite(target) || target < 0) {
        return;
    }

    const duration = 1300;
    const start = performance.now();

    function tick(now) {
        const elapsed = now - start;
        const progress = Math.min(elapsed / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        node.textContent = String(Math.floor(target * eased));

        if (progress < 1) {
            requestAnimationFrame(tick);
        } else {
            node.textContent = String(target);
        }
    }

    requestAnimationFrame(tick);
}

const counterNodes = document.querySelectorAll(".counter[data-count]");
counterNodes.forEach((counter) => animateCounter(counter));

function createBubble(role, text, options = {}) {
    const bubble = document.createElement("div");
    bubble.classList.add("chat-bubble", role === "user" ? "chat-user" : "chat-assistant");

    if (options.isTyping) {
        bubble.innerHTML = '<span class="chat-typing"><span></span><span></span><span></span></span>';
    } else {
        bubble.textContent = text;
    }

    return bubble;
}

function initAssistantChat() {
    const chatWindow = document.getElementById("chatWindow");
    const chatForm = document.getElementById("chatForm");
    const chatInput = document.getElementById("chatInput");
    const promptButtons = document.querySelectorAll("[data-chat-prompt]");

    if (!chatWindow || !chatForm || !chatInput) {
        return;
    }

    const addBubble = (role, text, options = {}) => {
        const bubble = createBubble(role, text, options);
        chatWindow.appendChild(bubble);
        chatWindow.scrollTop = chatWindow.scrollHeight;
        return bubble;
    };

    const ensureNonEmptyPlaceholder = () => {
        if (chatWindow.childElementCount === 0) {
            const placeholder = document.createElement("div");
            placeholder.className = "chat-empty";
            placeholder.innerHTML = "<p>Ask anything about endangered species, organizations, shop impact, or donations.</p>";
            chatWindow.appendChild(placeholder);
        }
    };

    const clearPlaceholder = () => {
        const placeholder = chatWindow.querySelector(".chat-empty");
        if (placeholder) {
            placeholder.remove();
        }
    };

    const loadHistory = async () => {
        try {
            const response = await fetch("/api/chat/history", {
                method: "GET",
                headers: {
                    "Accept": "application/json",
                },
            });

            if (!response.ok) {
                ensureNonEmptyPlaceholder();
                return;
            }

            const history = await response.json();
            if (!Array.isArray(history) || history.length === 0) {
                ensureNonEmptyPlaceholder();
                return;
            }

            clearPlaceholder();
            history.forEach((item) => {
                if (!item || typeof item.content !== "string" || typeof item.role !== "string") {
                    return;
                }
                addBubble(item.role === "user" ? "user" : "assistant", item.content);
            });
        } catch (_error) {
            ensureNonEmptyPlaceholder();
        }
    };

    const sendMessage = async (message) => {
        clearPlaceholder();
        addBubble("user", message);
        const typingBubble = addBubble("assistant", "", { isTyping: true });

        try {
            const response = await fetch("/api/chat", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                body: JSON.stringify({ message }),
            });

            typingBubble.remove();

            if (!response.ok) {
                const payload = await response.json().catch(() => ({}));
                addBubble("assistant", payload.error || "Unable to process your request right now.");
                return;
            }

            const payload = await response.json();
            const reply = typeof payload.reply === "string" ? payload.reply : "I could not generate a response.";
            addBubble("assistant", reply);

            if (Array.isArray(payload.suggestions) && payload.suggestions.length > 0) {
                payload.suggestions.slice(0, 3).forEach((suggestion) => {
                    if (typeof suggestion !== "string" || suggestion.length === 0) {
                        return;
                    }
                    const hint = document.createElement("button");
                    hint.type = "button";
                    hint.className = "prompt-chip mt-2";
                    hint.textContent = suggestion;
                    hint.addEventListener("click", () => {
                        chatInput.value = suggestion;
                        chatInput.focus();
                    });
                    chatWindow.appendChild(hint);
                });
                chatWindow.scrollTop = chatWindow.scrollHeight;
            }
        } catch (_error) {
            typingBubble.remove();
            addBubble("assistant", "Network error. Please try again in a moment.");
        }
    };

    chatForm.addEventListener("submit", async (event) => {
        event.preventDefault();
        const message = chatInput.value.trim();
        if (!message) {
            return;
        }
        chatInput.value = "";
        await sendMessage(message);
    });

    promptButtons.forEach((button) => {
        button.addEventListener("click", async () => {
            const prompt = button.getAttribute("data-chat-prompt") || "";
            const message = prompt.trim();
            if (!message) {
                return;
            }
            clearPlaceholder();
            openWidget();
            await sendMessage(message);
        });
    });

    // ------------------------------------------------------------------
    // Floating widget open/close (Guardian Buddy is on every page)
    // ------------------------------------------------------------------
    const fab = document.getElementById("aiFab");
    const widget = document.getElementById("aiWidget");
    const closeBtn = document.getElementById("aiClose");
    let historyLoaded = false;

    function openWidget() {
        if (!widget || !fab) {
            return;
        }
        widget.classList.add("is-open");
        widget.setAttribute("aria-hidden", "false");
        fab.classList.add("is-hidden");
        if (!historyLoaded) {
            historyLoaded = true;
            loadHistory();
        }
        window.setTimeout(() => chatInput.focus(), 240);
    }

    function closeWidget() {
        if (!widget || !fab) {
            return;
        }
        widget.classList.remove("is-open");
        widget.setAttribute("aria-hidden", "true");
        fab.classList.remove("is-hidden");
    }

    if (fab) {
        fab.addEventListener("click", openWidget);
    }
    if (closeBtn) {
        closeBtn.addEventListener("click", closeWidget);
    }
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape" && widget && widget.classList.contains("is-open")) {
            closeWidget();
            fab && fab.focus();
        }
    });

    ensureNonEmptyPlaceholder();
}

initAssistantChat();

/* ----------------------------------------------------------------------
   Toast notifications
---------------------------------------------------------------------- */
function showToast(message, variant = "success") {
    const stack = document.getElementById("toastStack");
    if (!stack) {
        return;
    }

    const toast = document.createElement("div");
    toast.className = `toast${variant === "error" ? " toast-error" : ""}`;
    toast.setAttribute("role", "status");

    const iconId = variant === "error" ? "i-info" : "i-check";
    const icon = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    icon.setAttribute("class", "icon");
    const use = document.createElementNS("http://www.w3.org/2000/svg", "use");
    use.setAttribute("href", `#${iconId}`);
    icon.appendChild(use);

    const text = document.createElement("span");
    text.textContent = message;

    toast.append(icon, text);
    stack.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add("is-visible"));

    window.setTimeout(() => {
        toast.classList.remove("is-visible");
        window.setTimeout(() => toast.remove(), 320);
    }, 3200);
}

/* ----------------------------------------------------------------------
   Quantity steppers
---------------------------------------------------------------------- */
function initQuantitySteppers() {
    document.querySelectorAll("[data-qty-stepper]").forEach((stepper) => {
        const input = stepper.querySelector("input[name='quantity']");
        if (!input) {
            return;
        }

        const clamp = (value) => {
            const min = Number(input.min || "1");
            const max = input.max ? Number(input.max) : Infinity;
            if (!Number.isFinite(value)) {
                return min;
            }
            return Math.min(Math.max(value, min), max);
        };

        const decrement = stepper.querySelector("[data-qty-decrement]");
        const increment = stepper.querySelector("[data-qty-increment]");

        if (decrement) {
            decrement.addEventListener("click", () => {
                input.value = String(clamp(Number(input.value || "0") - 1));
            });
        }
        if (increment) {
            increment.addEventListener("click", () => {
                input.value = String(clamp(Number(input.value || "0") + 1));
            });
        }
        input.addEventListener("change", () => {
            input.value = String(clamp(Number(input.value || "0")));
        });
    });
}

initQuantitySteppers();

/* ----------------------------------------------------------------------
   Animal Quiz game
---------------------------------------------------------------------- */
function initQuiz() {
    const mount = document.getElementById("quizApp");
    const dataNode = document.getElementById("quizData");
    if (!mount || !dataNode) {
        return;
    }

    let questions = [];
    try {
        questions = JSON.parse(dataNode.textContent || "[]");
    } catch (_error) {
        questions = [];
    }
    if (!Array.isArray(questions) || questions.length === 0) {
        return;
    }

    const letters = ["A", "B", "C", "D"];
    let current = 0;
    let score = 0;
    let locked = false;

    const encourage = (isCorrect) =>
        isCorrect
            ? ["Woohoo! That's right! 🎉", "Awesome job! 🌟", "You got it! 🥳", "Brilliant! 🐾"][Math.floor(Math.random() * 4)]
            : "Good try! Let's learn this one together. 💚";

    function render() {
        const q = questions[current];
        const total = questions.length;
        const badge = q.category === "Ocean" ? "🌊 Ocean" : "🌿 Land";

        const optionsHtml = q.options
            .map(
                (option, index) =>
                    `<button type="button" class="quiz-option" data-index="${index}">
                        <span class="opt-key">${q.type === "tf" ? (index === 0 ? "✓" : "✗") : letters[index]}</span>
                        <span>${option}</span>
                    </button>`
            )
            .join("");

        mount.innerHTML = `
            <div class="quiz-progress">
                <span>${badge}</span>
                <span>Question ${current + 1} of ${total}</span>
                <span>Score: ${score}</span>
            </div>
            <div class="quiz-progress-bar"><i style="width:${((current) / total) * 100}%"></i></div>
            <h2 class="quiz-question font-display">${q.question}</h2>
            <div class="quiz-options">${optionsHtml}</div>
            <div class="quiz-feedback" id="quizFeedback"></div>
            <div class="quiz-actions" id="quizActions"></div>
        `;

        locked = false;
        mount.querySelectorAll(".quiz-option").forEach((button) => {
            button.addEventListener("click", () => handleAnswer(button));
        });
    }

    function handleAnswer(button) {
        if (locked) {
            return;
        }
        locked = true;

        const q = questions[current];
        const chosen = Number(button.dataset.index);
        const correctIndex = q.answer_index;
        const isCorrect = chosen === correctIndex;

        if (isCorrect) {
            score += 1;
        }

        mount.querySelectorAll(".quiz-option").forEach((node) => {
            const idx = Number(node.dataset.index);
            node.disabled = true;
            if (idx === correctIndex) {
                node.classList.add("is-correct");
            } else if (idx === chosen) {
                node.classList.add("is-wrong");
            }
        });

        const feedback = document.getElementById("quizFeedback");
        if (feedback) {
            feedback.textContent = encourage(isCorrect);
            feedback.classList.add("show", isCorrect ? "good" : "bad");
        }

        const actions = document.getElementById("quizActions");
        if (actions) {
            const isLast = current === questions.length - 1;
            const nextBtn = document.createElement("button");
            nextBtn.type = "button";
            nextBtn.className = "btn-primary";
            nextBtn.innerHTML = isLast
                ? 'See my score<svg class="icon"><use href="#i-star"></use></svg>'
                : 'Next question<svg class="icon"><use href="#i-arrow-right"></use></svg>';
            nextBtn.addEventListener("click", () => {
                if (isLast) {
                    showResult();
                } else {
                    current += 1;
                    render();
                }
            });
            actions.appendChild(nextBtn);
        }
    }

    function showResult() {
        const total = questions.length;
        const pct = Math.round((score / total) * 100);
        let emoji = "🌟";
        let title = "Great effort!";
        if (pct === 100) {
            emoji = "🏆";
            title = "Perfect score! You are an Animal Hero!";
        } else if (pct >= 70) {
            emoji = "🎉";
            title = "Amazing work, Guardian!";
        } else if (pct >= 40) {
            emoji = "🐾";
            title = "Nice job! Keep learning!";
        } else {
            emoji = "🌱";
            title = "Good start! Try again to grow your score!";
        }

        mount.innerHTML = `
            <div class="quiz-result">
                <div class="quiz-emoji-big">${emoji}</div>
                <p class="score-badge">${score} / ${total}</p>
                <h2 class="font-display text-2xl mt-2">${title}</h2>
                <p class="mt-2 text-ink-soft">You answered ${pct}% correctly. Every question helps our planet's animals! 💚</p>
                <div class="quiz-actions mt-5">
                    <button type="button" class="btn-primary" id="quizRestart"><svg class="icon"><use href="#i-star"></use></svg>Play again</button>
                    <a href="/animals" class="btn-secondary"><svg class="icon"><use href="#i-paw"></use></svg>Meet the animals</a>
                </div>
            </div>
        `;

        const restart = document.getElementById("quizRestart");
        if (restart) {
            restart.addEventListener("click", () => {
                current = 0;
                score = 0;
                render();
            });
        }
    }

    render();
}

initQuiz();

/* ----------------------------------------------------------------------
   AJAX add-to-cart (no page refresh)
---------------------------------------------------------------------- */
function bumpCartCount(count) {
    document.querySelectorAll(".cart-count").forEach((node) => {
        node.textContent = String(count);
        node.classList.remove("is-bumped");
        // Force reflow so the animation can replay
        void node.offsetWidth;
        node.classList.add("is-bumped");
    });
}

function initAddToCart() {
    document.querySelectorAll("form.js-add-to-cart").forEach((form) => {
        form.addEventListener("submit", async (event) => {
            event.preventDefault();

            const button = form.querySelector("button[type='submit']");
            if (button && button.disabled) {
                return;
            }

            const originalHtml = button ? button.innerHTML : "";
            if (button) {
                button.disabled = true;
            }

            try {
                const response = await fetch(form.action, {
                    method: "POST",
                    headers: {
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json",
                    },
                    body: new FormData(form),
                });

                if (!response.ok) {
                    throw new Error("Request failed");
                }

                const payload = await response.json();

                if (typeof payload.cart_item_count === "number") {
                    bumpCartCount(payload.cart_item_count);
                }

                showToast(payload.message || "Added to cart.", "success");

                if (button) {
                    button.innerHTML = '<svg class="icon"><use href="#i-check"></use></svg>Added';
                    button.classList.add("is-added");
                    window.setTimeout(() => {
                        button.innerHTML = originalHtml;
                        button.classList.remove("is-added");
                        button.disabled = false;
                    }, 1400);
                }
            } catch (_error) {
                showToast("Could not add to cart. Please try again.", "error");
                if (button) {
                    button.innerHTML = originalHtml;
                    button.disabled = false;
                }
            }
        });
    });
}

initAddToCart();
