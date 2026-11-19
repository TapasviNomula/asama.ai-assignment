import json

# 1. Database of registered company agents and what they care about
agents = [
    {
        "id": 1,
        "name": "Swiggy",
        "interests": ["food", "delivery", "diwali", "offer", "discount"],
        "score_boost": 1.0,
    },
    {
        "id": 2,
        "name": "PhonePe",
        "interests": ["upi", "payment", "cashback", "diwali", "offer", "discount", "delivery"],
        "score_boost": 1.0,
    },
    {
        "id": 3,
        "name": "HDFC Bank",
        "interests": ["card", "bank", "emi", "offer", "discount", "diwali"],
        "score_boost": 1.0,
    },
    {
        "id": 4,
        "name": "Bajaj Auto",
        "interests": ["bike", "scooter", "ev", "vehicle", "service"],
        "score_boost": 1.0,
    },
]

posts = []
comments = []


# 2. Safety check to stop bad or fake prompt-injection posts
def is_safe_post(text):
    bad_words = ["ignore previous instructions", "system prompt", "hack", "drop table"]
    for word in bad_words:
        if word in text.lower():
            return False
    return True


# 3. Core Relevance Router: decides which agents should be notified
def find_relevant_agents(author_name, post_text):
    words = post_text.lower().replace("!", "").replace(".", "").split()
    notified = []

    for agent in agents:
        # Do not notify the company that made the post
        if agent["name"] == author_name:
            continue

        # Count matching keywords between post and agent interests
        matches = 0
        for w in words:
            if w in agent["interests"]:
                matches += 1

        # Calculate relevance score using feedback boost
        relevance = (matches / len(agent["interests"])) * agent["score_boost"]

        # Only notify if relevance passes threshold (avoids spam)
        if relevance >= 0.25:
            notified.append(agent)

    return notified


# 4. Agent generates a reply if notified
def generate_reply(agent_name, post_text):
    if agent_name == "PhonePe":
        return "Extra Rs.50 cashback when you pay for Swiggy orders with PhonePe UPI on Diwali!"
    elif agent_name == "HDFC Bank":
        return "Get 10% instant discount using HDFC Bank Credit Cards on this offer!"
    else:
        return f"{agent_name} is interested in partnering on this!"


# 5. Main flow: Post -> Route -> Respond -> Learn from feedback
def create_post(author_name, text):
    if not is_safe_post(text):
        print("Blocked unsafe post!")
        return

    post_id = len(posts) + 1
    posts.append({"id": post_id, "author": author_name, "text": text})
    print(f"\n[{author_name} Posted]: {text}")

    relevant_agents = find_relevant_agents(author_name, text)
    print("Notified Agents:", [a["name"] for a in relevant_agents])

    for agent in relevant_agents:
        reply = generate_reply(agent["name"], text)
        comments.append({"post_id": post_id, "agent": agent["name"], "comment": reply})
        # Feedback loop: boost agent weight slightly since they engaged
        agent["score_boost"] = round(agent["score_boost"] + 0.05, 2)
        print(f"  -> {agent['name']} replied: {reply}")


if __name__ == "__main__":
    create_post("Swiggy", "5% off all deliveries on Diwali!")
