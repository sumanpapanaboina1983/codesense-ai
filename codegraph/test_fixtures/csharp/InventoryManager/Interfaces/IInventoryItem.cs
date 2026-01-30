namespace InventoryManager.Interfaces
{
    /// <summary>
    /// Interface for inventory items
    /// </summary>
    public interface IInventoryItem
    {
        int Id { get; set; }
        string Name { get; set; }
        int Quantity { get; set; }
        decimal Price { get; set; }

        decimal GetTotalValue();
        bool IsInStock();
    }
}
