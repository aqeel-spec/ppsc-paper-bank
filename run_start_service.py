"""
Convenience script for running the Start Service with different options.
"""

from app.services.start_service import StartService, run_start_process, run_individual_step
import sys

def main():
    """Main function to handle command line arguments or interactive mode."""
    
    if len(sys.argv) > 1:
        # Command line mode
        command = sys.argv[1].lower()
        
        if command == 'all':
            print("Running complete start process...")
            run_start_process()
        elif command.startswith('step'):
            try:
                step_num = int(command.replace('step', ''))
                if 1 <= step_num <= 5:
                    print(f"Running Step {step_num}...")
                    result = run_individual_step(step_num)
                    if result['success']:
                        print(f"✅ Step {step_num} completed successfully")
                    else:
                        print(f"❌ Step {step_num} failed: {result.get('error')}")
                else:
                    print("❌ Invalid step number. Use step1, step2, step3, step4, or step5")
            except ValueError:
                print("❌ Invalid step format. Use step1, step2, step3, step4, or step5")
        else:
            show_help()
    else:
        # Interactive mode
        show_menu()

def show_help():
    """Show help information."""
    print("""
🚀 Start Service Command Line Usage:

python run_start_service.py [command]

Commands:
  all     - Run complete start process (all 5 steps)
  step1   - Insert unique websites only
  step2   - Create website records with flags only
  step3   - Process TopBar websites only
  step4   - Process PaperExit websites only (future feature)
  step5   - Process SideBar websites only (future feature)

Examples:
  python run_start_service.py all
  python run_start_service.py step1
  python run_start_service.py step3
""")

def show_menu():
    """Show interactive menu."""
    while True:
        print("""
🚀 START SERVICE INTERACTIVE MENU
================================

1. Run Complete Process (All Steps)
2. Step 1: Insert Unique Websites
3. Step 2: Create Website Records  
4. Step 3: Process TopBar Websites
5. Step 4: Process PaperExit (Future)
6. Step 5: Process SideBar (Future)
7. Show Process Flow
8. Exit

Choose an option (1-8): """, end="")
        
        try:
            choice = input().strip()
            
            if choice == '1':
                print("\n🚀 Running Complete Process...")
                run_start_process()
                
            elif choice == '2':
                print("\n🌐 Running Step 1: Insert Unique Websites...")
                result = run_individual_step(1)
                print("✅ Step 1 completed" if result['success'] else f"❌ Step 1 failed: {result.get('error')}")
                
            elif choice == '3':
                print("\n🏭 Running Step 2: Create Website Records...")
                result = run_individual_step(2)
                print("✅ Step 2 completed" if result['success'] else f"❌ Step 2 failed: {result.get('error')}")
                
            elif choice == '4':
                print("\n📊 Running Step 3: Process TopBar Websites...")
                result = run_individual_step(3)
                print("✅ Step 3 completed" if result['success'] else f"❌ Step 3 failed: {result.get('error')}")
                
            elif choice == '5':
                print("\n📄 Running Step 4: Process PaperExit (Future)...")
                result = run_individual_step(4)
                print("✅ Step 4 completed" if result['success'] else f"❌ Step 4 failed: {result.get('error')}")
                
            elif choice == '6':
                print("\n📋 Running Step 5: Process SideBar (Future)...")
                result = run_individual_step(5)
                print("✅ Step 5 completed" if result['success'] else f"❌ Step 5 failed: {result.get('error')}")
                
            elif choice == '7':
                show_process_flow()
                
            elif choice == '8':
                print("👋 Exiting...")
                break
                
            else:
                print("❌ Invalid choice. Please select 1-8.")
                
        except KeyboardInterrupt:
            print("\n\n👋 Exiting...")
            break
        except Exception as e:
            print(f"\n❌ Error: {str(e)}")

def show_process_flow():
    """Show the complete process flow."""
    print("""
📋 START SERVICE PROCESS FLOW
=============================

1. 🌐 WEBSITES (Step 1)
   └── Insert unique websites without duplicates
   └── Websites: PakMcqs, TestPoint
   └── Purpose: Define which websites we scrape from

2. 🏭 WEBSITE (Step 2)  
   └── Create Website records with processing flags
   └── Flags: is_top_bar, is_paper_exit, is_side_bar
   └── Purpose: Control which processing services to run

3. 📊 TOP BAR PROCESSING (Step 3)
   └── Process websites where is_top_bar = True
   └── Uses: start_urls service for URL collection
   └── Purpose: Collect navigation URLs from website top bars

4. 📄 PAPER EXIT PROCESSING (Step 4) [Future]
   └── Process websites where is_paper_exit = True
   └── Uses: TBD - paper extraction services
   └── Purpose: Extract paper/test content from websites

5. 📋 SIDEBAR PROCESSING (Step 5) [Future]
   └── Process websites where is_side_bar = True  
   └── Uses: TBD - sidebar navigation services
   └── Purpose: Extract sidebar navigation content

🎯 CURRENT STATUS:
   ✅ Steps 1-3: Fully implemented and working
   🚧 Steps 4-5: Placeholder for future development

🔄 FLOW SUMMARY:
   Websites → Website Records → Conditional Processing
   
📊 RESULTS:
   - Prevents duplicate website creation
   - Enables selective processing based on flags
   - Provides foundation for future service expansion
""")

if __name__ == "__main__":
    main()
