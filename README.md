# EuroConvectRAG

A local, privacy-focused RAG tool that turns historical ESTOFEX forecasts into an AI discussion partner for weather and climate research. By ingesting hundreds of forecast discussions and mesoscale updates, it synthesizes operational meteorologists' process-based physical reasoning across convective events.

## Core Objective

Serve as an interactive research partner that helps scientists synthesize synoptic patterns, mesoscale mechanisms, and forecaster reasoning across large historical archives of European convective storm forecasts.

## Key Features

- **Automated Ingestion:** Scrapes and parses warm-season ESTOFEX forecasts and mesoscale discussions into clean text formats.
- **Synthesized Research Partner:** Cross-references hundreds of historical forecasts to discuss synoptic setups, atmospheric physics, and regional storm dynamics.
- **Privacy & Local Execution:** Runs completely offline on local hardware or institute clusters using Ollama and open-source models (e.g., Llama 3.1, Llama 3.2, Gemma 3).
- **Zero-Hallucination Query Mode:** Restricts responses strictly to retrieved forecaster texts to preserve scientific accuracy.

## Repository Structure