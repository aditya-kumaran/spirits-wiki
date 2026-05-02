# Wiki Editing Guide

## Wiki Links

To link to another wiki page, use double-bracket syntax:

```
[[Entity Name]]
```

For example:
```
[[Catherine Stormborn]] traveled to [[Dubai]] with [[Jacob]].
```

This will render as clickable links to the respective wiki pages. If the target page exists, it will appear as a colored link. If the page does not exist, it will appear as plain text.

**Tips:**
- Use the exact entity name as it appears on the wiki page (case-insensitive matching is used for the URL slug)
- Entity names are automatically converted to URL-safe slugs (e.g., "Catherine Stormborn" becomes `/wiki/catherine-stormborn`)

## Markdown Support

The editor supports standard Markdown syntax:

### Headings
```
## Section Heading
### Subsection
```

### Bold and Italic
```
**bold text**
*italic text*
```

### Lists
```
- Bullet item
- Another item

1. Numbered item
2. Another item
```

### Tables
```
| Column 1 | Column 2 |
|----------|----------|
| Cell 1   | Cell 2   |
```

## Citations

Citations use footnote syntax. Inline references appear as superscript numbers that link to the References section at the bottom of the page:

```
Catherine gained control of the city. [^1]

## References
[^1]: **Spirits_Faces.docx**, §Characters > Catherine — "She gained influence and took control of the city"
```

Each `[^N]` in the text corresponds to entry `N` in the References section. Click any citation number to jump to its source.

## Images

Images can be uploaded directly from the wiki page view or from the edit page. You can also embed images using standard Markdown:

```
![Alt text](/uploads/image-name.png)
```

## Entity Types

Each page has an entity type (character, location, event, etc.) that determines the suggested section structure. You can change the entity type from the page view by clicking on the type badge.
