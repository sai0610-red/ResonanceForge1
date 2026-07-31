from src.graph import graph

if __name__ == "__main__":
    question = input("\nEnter your question: ")
    
    result = graph.invoke({
        "user_question": question,
        "diagnosis": "",
        "architecture": "",
        "generated_code": "",
        "critique": "",
        "final_answer": ""
    })
    
    print(result["final_answer"])