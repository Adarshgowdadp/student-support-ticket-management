# Manual Test Checklist

1. Login as student.
2. Verify student sees only own tickets.
3. Create a new ticket.
4. Verify category SLA creates a due time.
5. Add a public comment.
6. Login as staff.
7. Verify staff sees the ticket.
8. Assign ticket to staff.
9. Change priority and status.
10. Add an internal note.
11. Login as student and verify the internal note is hidden.
12. Verify dashboard counts update.
13. Open an overdue active ticket and verify `SLA BREACHED` appears.
14. Resolve then close the ticket.
15. Try invalid status/priority or a non-staff assignee and verify API rejection.
