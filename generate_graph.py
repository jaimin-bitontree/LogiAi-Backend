from agent.workflow import graph
import os
import logging

logger = logging.getLogger(__name__)

def generate():
    try:
        # Generate Mermaid PNG bytes
        png_bytes = graph.get_graph().draw_mermaid_png()
        
        # Save to file
        output_path = "workflow_graph.png"
        with open(output_path, "wb") as f:
            f.write(png_bytes)
            
        logger.info(f"✅ Graph image generated: {os.path.abspath(output_path)}")
    except Exception as e:
        logger.error(f"❌ Failed to generate graph: {e}")
        logger.info("Note: You might need to install 'pygraphviz', 'pydot', or 'graphviz' for PNG generation.")
        logger.info("Alternative: Generating Mermaid text representation...")
        try:
            mermaid_text = graph.get_graph().draw_mermaid()
            with open("workflow_graph.md", "w") as f:
                f.write(f"```mermaid\n{mermaid_text}\n```")
            logger.info("✅ Mermaid representation saved to workflow_graph.md")
        except:
             logger.error("❌ Even Mermaid generation failed.")

if __name__ == "__main__":
    generate()
