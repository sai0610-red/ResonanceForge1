from typing import TypedDict
from langgraph.graph import StateGraph, START, END
from langchain_groq import ChatGroq
from dotenv import load_dotenv

load_dotenv()

llm = ChatGroq(model="llama-3.3-70b-versatile", temperature=0)

class State(TypedDict):
    user_question: str
    diagnosis: str
    architecture: str
    generated_code: str
    critique: str
    final_answer: str

def receive_question(state: State):
    print("→ 1. Received question")
    return {"user_question": state["user_question"]}

def diagnostician_agent(state: State):
    print("→ 2. Diagnostician Agent analyzing...")
    prompt = f"""You are the Diagnostician Agent of ResonanceForge.
You evaluate companies using Capgemini’s Resonance Framework.

Pillars:
- ACCESS (Data, Tech, Talent)
- ADAPT (Processes, Culture, Change readiness)
- ADOPT (Strategy, Pilots, Scaling)

User Question: {state['user_question']}

Respond in this exact structure:

**AI Readiness Diagnosis**

**ACCESS:** X/10
Reason: ...

**ADAPT:** X/10
Reason: ...

**ADOPT:** X/10
Reason: ...

**Overall Readiness:** Low / Medium / High

**Top 3 Gaps:**
1. ...
2. ...
3. ...
"""
    response = llm.invoke(prompt)
    return {"diagnosis": response.content}

def architect_agent(state: State):
    print("→ 3. Architect Agent designing solution...")
    prompt = f"""You are the Architect Agent of ResonanceForge.
Based on the diagnosis below, design a practical multi-agent architecture using LangGraph.

Diagnosis:
{state['diagnosis']}

Provide:
1. Recommended agents and their responsibilities
2. High-level flow (how agents talk to each other)
3. Why this architecture fits the company’s readiness level
Keep it clear and professional.
"""
    response = llm.invoke(prompt)
    return {"architecture": response.content}

def code_generator_agent(state: State):
    print("→ 4. Code Generator Agent writing LangGraph code...")
    prompt = f"""You are a senior LangGraph engineer.

Based on this architecture:
{state['architecture']}

Generate clean, correct, and runnable LangGraph code.

STRICT RULES (follow exactly):
1. Start with these imports only:
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

2. Define a TypedDict called State
3. Create normal Python functions as nodes (not classes)
4. Use this pattern only:
   builder = StateGraph(State)
   builder.add_node("node_name", function_name)
   builder.add_edge(START, "first_node")
   builder.add_edge("node_a", "node_b")
   builder.add_edge("last_node", END)
   graph = builder.compile()

5. Do NOT use GraphBuilder, Agent class, or fake methods
6. Do NOT invent non-existent LangGraph features
7. Output ONLY the Python code — no explanations

Generate a simple but correct multi-node example based on the architecture.
"""
    response = llm.invoke(prompt)
    return {"generated_code": response.content}

def critic_agent(state: State):
    print("→ 5. Critic Agent reviewing everything...")
    prompt = f"""You are the Critic Agent of ResonanceForge.
Review the diagnosis, architecture, and generated code.

Diagnosis:
{state['diagnosis']}

Architecture:
{state['architecture']}

Generated Code:
{state['generated_code']}

Give:
1. Strengths
2. Weaknesses / Risks
3. Concrete improvements
4. Final recommendation (Ready for pilot / Needs work / Not ready)
"""
    response = llm.invoke(prompt)
    return {"critique": response.content}

def final_compiler(state: State):
    print("→ 6. Compiling final ResonanceForge report...")
    final = f"""
===========================================
       RESONANCEFORGE FINAL REPORT
===========================================

USER QUESTION:
{state['user_question']}

-------------------------------------------
1. DIAGNOSIS (Diagnostician Agent)
-------------------------------------------
{state['diagnosis']}

-------------------------------------------
2. ARCHITECTURE (Architect Agent)
-------------------------------------------
{state['architecture']}

-------------------------------------------
3. GENERATED LANGGRAPH CODE (Code Generator)
-------------------------------------------
{state['generated_code']}

-------------------------------------------
4. CRITIQUE & RECOMMENDATION (Critic Agent)
-------------------------------------------
{state['critique']}

===========================================
"""
    return {"final_answer": final}

# Build the graph
builder = StateGraph(State)

builder.add_node("receive_question", receive_question)
builder.add_node("diagnostician_agent", diagnostician_agent)
builder.add_node("architect_agent", architect_agent)
builder.add_node("code_generator_agent", code_generator_agent)
builder.add_node("critic_agent", critic_agent)
builder.add_node("final_compiler", final_compiler)

builder.add_edge(START, "receive_question")
builder.add_edge("receive_question", "diagnostician_agent")
builder.add_edge("diagnostician_agent", "architect_agent")
builder.add_edge("architect_agent", "code_generator_agent")
builder.add_edge("code_generator_agent", "critic_agent")
builder.add_edge("critic_agent", "final_compiler")
builder.add_edge("final_compiler", END)

graph = builder.compile()