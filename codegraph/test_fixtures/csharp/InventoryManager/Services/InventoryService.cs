using System.Collections.Generic;
using InventoryManager.Interfaces;

namespace InventoryManager.Services
{
    /// <summary>
    /// Service for managing inventory items
    /// </summary>
    public class InventoryService
    {
        private readonly List<IInventoryItem> _items = new List<IInventoryItem>();

        public void AddItem(IInventoryItem item)
        {
            _items.Add(item);
        }

        public void RemoveItem(int id)
        {
            _items.RemoveAll(x => x.Id == id);
        }

        public IInventoryItem GetItem(int id)
        {
            return _items.Find(x => x.Id == id);
        }

        public IEnumerable<IInventoryItem> GetAllItems()
        {
            return _items;
        }

        public int GetTotalCount()
        {
            return _items.Count;
        }
    }
}
