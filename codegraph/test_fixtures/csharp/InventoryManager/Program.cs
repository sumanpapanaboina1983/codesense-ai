// Inventory Manager Application

using InventoryManager.Models;
using InventoryManager.Services;
using InventoryManager.Interfaces;

namespace InventoryManager
{
    // Line 9
    // Line 10
    class Program
    {
        // Line 13
        static void Main(string[] args)
        {
            Console.WriteLine("Inventory Manager v1.0");
            Console.WriteLine("======================");

            // Create inventory service
            var inventoryService = new InventoryService();

            // Add some sample products
            var product1 = new Product
            {
                Id = 1,
                Name = "Laptop",
                Quantity = 10,
                Price = 999.99m
            };

            var product2 = new Product
            {
                Id = 2,
                Name = "Mouse",
                Quantity = 50,
                Price = 29.99m
            };

            inventoryService.AddItem(product1);
            inventoryService.AddItem(product2);

            // Display inventory
            Console.WriteLine("\nCurrent Inventory:");
            foreach (var item in inventoryService.GetAllItems())
            {
                Console.WriteLine($"  {item.Name}: {item.Quantity} units @ ${item.Price}");
            }

            Console.WriteLine("\nPress any key to exit...");
            Console.ReadKey();
        }
    }
}
