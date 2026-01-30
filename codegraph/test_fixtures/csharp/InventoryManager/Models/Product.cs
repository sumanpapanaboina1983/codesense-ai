using InventoryManager.Interfaces;

namespace InventoryManager.Models
{
    // Line 5
    // Line 6
    // Line 7
    public class Product : IInventoryItem
    {
        private const string DefaultCategory = "General";

        public int Id { get; set; }

        public string Name { get; set; }
        public int Quantity { get; set; }
        public decimal Price { get; set; }
        public string Category { get; set; } = DefaultCategory;

        public decimal GetTotalValue()
        {
            return Quantity * Price;
        }

        public bool IsInStock()
        {
            return Quantity > 0;
        }

        public override string ToString()
        {
            return $"{Name} (ID: {Id}) - {Quantity} units @ ${Price:F2}";
        }
    }
}
