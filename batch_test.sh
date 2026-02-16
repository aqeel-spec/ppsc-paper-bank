#!/bin/bash
# Batch MCQ Collection Script
# Generated on 2025-07-19 17:22:46
# URLs to process: 3

echo "🚀 Starting batch MCQ collection..."
echo "📊 Processing 3 URLs"


echo "🔄 [1/3] Processing: PPSC Assistant Past Paper 27-04-2025"
python -m app.services.scrapper.paper_mcqs_collector_v1 "https://testpointpk.com/paper-mcqs/5766/ppsc-assistant-past-paper-27-04-2025"

if [ $? -eq 0 ]; then
    echo "✅ [1/3] Success: PPSC Assistant Past Paper 27-04-2025"
else
    echo "❌ [1/3] Failed: PPSC Assistant Past Paper 27-04-2025"
fi

echo "⏳ Waiting 2 seconds before next URL..."
sleep 2

echo "🔄 [2/3] Processing: PPSC Assistant Syllabus"
python -m app.services.scrapper.paper_mcqs_collector_v1 "https://testpointpk.com/paper-mcqs/5760/ppsc-assistant-syllabus"

if [ $? -eq 0 ]; then
    echo "✅ [2/3] Success: PPSC Assistant Syllabus"
else
    echo "❌ [2/3] Failed: PPSC Assistant Syllabus"
fi

echo "⏳ Waiting 2 seconds before next URL..."
sleep 2

echo "🔄 [3/3] Processing: PPSC Assistant Past Paper 01-12-2024 (Morning)"
python -m app.services.scrapper.paper_mcqs_collector_v1 "https://testpointpk.com/paper-mcqs/5303/ppsc-assistant-past-paper-01-12-2024-(morning)"

if [ $? -eq 0 ]; then
    echo "✅ [3/3] Success: PPSC Assistant Past Paper 01-12-2024 (Morning)"
else
    echo "❌ [3/3] Failed: PPSC Assistant Past Paper 01-12-2024 (Morning)"
fi

echo "⏳ Waiting 2 seconds before next URL..."
sleep 2

echo "🎉 Batch collection completed!"
echo "📊 Processed 3 URLs"
