/******************************************************************************
 * The MIT License (MIT)
 *
 * Copyright (c) 2026 Baldur Karlsson
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
 ******************************************************************************/

#include "TAPassDrawDiff.h"
#include <QApplication>
#include <QFile>
#include <QFileDialog>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QPushButton>
#include <QSpinBox>
#include <QTextStream>
#include <QToolButton>
#include <QVBoxLayout>
#include "Code/QRDUtils.h"
#include "Code/Resources.h"

static const ShaderStage DiffStages[] = {
    ShaderStage::Vertex, ShaderStage::Hull, ShaderStage::Domain, ShaderStage::Geometry,
    ShaderStage::Pixel,  ShaderStage::Compute, ShaderStage::Amplification, ShaderStage::Mesh,
};

static QString DiffStageName(ICaptureContext &ctx, ShaderStage stage)
{
  return ToQStr(stage, ctx.APIProps().pipelineType);
}

static QString ResourceLabel(ICaptureContext &ctx, ResourceId id)
{
  return id == ResourceId() ? QString() : QString(ctx.GetResourceName(id));
}

static QString BufferLabel(ICaptureContext &ctx, const BoundVBuffer &buffer)
{
  return QFormatStr("%1 offs=%2 stride=%3 size=%4")
      .arg(ResourceLabel(ctx, buffer.resourceId))
      .arg(buffer.byteOffset)
      .arg(buffer.byteStride)
      .arg(buffer.byteSize);
}


static QString DiffValueString(const ShaderVariable &var)
{
  if(!var.members.empty())
    return QApplication::translate("TAPassDrawDiff", "<struct/array>");

  QStringList rows;
  const uint32_t rowCount = qMax<uint32_t>(1, var.rows);
  const uint32_t colCount = qMax<uint32_t>(1, var.columns);

  for(uint32_t row = 0; row < rowCount; row++)
  {
    QStringList cols;
    for(uint32_t col = 0; col < colCount; col++)
    {
      uint32_t idx = row * colCount + col;
      switch(var.type)
      {
        case VarType::Float: cols << Formatter::Format(var.value.f32v[idx]); break;
        case VarType::Double: cols << Formatter::Format(var.value.f64v[idx]); break;
        case VarType::Half: cols << Formatter::Format(var.value.f16v[idx]); break;
        case VarType::SInt: cols << QString::number(var.value.s32v[idx]); break;
        case VarType::UInt: cols << QString::number(var.value.u32v[idx]); break;
        case VarType::SLong: cols << QString::number((qlonglong)var.value.s64v[idx]); break;
        case VarType::ULong: cols << QString::number((qulonglong)var.value.u64v[idx]); break;
        case VarType::SShort: cols << QString::number(var.value.s16v[idx]); break;
        case VarType::UShort: cols << QString::number(var.value.u16v[idx]); break;
        case VarType::SByte: cols << QString::number(var.value.s8v[idx]); break;
        case VarType::UByte: cols << QString::number(var.value.u8v[idx]); break;
        case VarType::Bool: cols << (var.value.u32v[idx] ? lit("true") : lit("false")); break;
        default: cols << QString::number((qulonglong)var.value.u64v[idx]); break;
      }
    }
    rows << cols.join(lit(", "));
  }

  return rows.join(lit("; "));
}

static void AddCBufferVariableRows(rdcarray<TAPassDrawDiff::DiffRow> &rows, const QString &stage,
                                   uint32_t slot, const rdcarray<ShaderVariable> &vars,
                                   const rdcstr &prefix)
{
  for(const ShaderVariable &var : vars)
  {
    rdcstr path = prefix.empty() ? var.name : prefix + "." + var.name;
    if(var.members.empty())
    {
      TAPassDrawDiff::DiffRow row;
      row.category = QApplication::translate("TAPassDrawDiff", "CBuffer Variables");
      row.name = QFormatStr("%1[%2].%3").arg(stage).arg(slot).arg(QString(path));
      row.b = DiffValueString(var);
      rows.push_back(row);
    }
    else
    {
      AddCBufferVariableRows(rows, stage, slot, var.members, path);
    }
  }
}

static QString DescriptorLabel(ICaptureContext &ctx, const UsedDescriptor &descriptor)
{
  const Descriptor &desc = descriptor.descriptor;
  QString resource = ResourceLabel(ctx, desc.resource);
  QString type = QString::number((uint32_t)descriptor.access.type);
  QString details = QFormatStr("%1 idx=%2 arr=%3")
                        .arg(type)
                        .arg(descriptor.access.index)
                        .arg(descriptor.access.arrayElement);

  if(desc.resource != ResourceId())
    details += QFormatStr(" res=%1 view=%2 offs=%3 size=%4 fmt=%5")
                   .arg(resource)
                   .arg(ResourceLabel(ctx, desc.view))
                   .arg(desc.byteOffset)
                   .arg(desc.byteSize)
                   .arg(desc.format.Name());

  return details;
}

TAPassDrawDiff::TAPassDrawDiff(ICaptureContext &ctx, QWidget *parent) : QFrame(parent), m_Ctx(ctx)
{
  setWindowTitle(tr("TA Pass/Draw Diff"));

  QVBoxLayout *root = new QVBoxLayout(this);
  root->setContentsMargins(3, 3, 3, 3);

  QHBoxLayout *toolbar = new QHBoxLayout();
  toolbar->setContentsMargins(0, 0, 0, 0);

  m_EventA = new QSpinBox(this);
  m_EventA->setRange(0, INT_MAX);
  m_EventB = new QSpinBox(this);
  m_EventB->setRange(0, INT_MAX);

  m_SetA = new QToolButton(this);
  m_SetA->setText(tr("Set A = Current"));
  m_SetA->setIcon(Icons::flag_green());
  m_SetA->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_SetB = new QToolButton(this);
  m_SetB->setText(tr("Set B = Current"));
  m_SetB->setIcon(Icons::flag_green());
  m_SetB->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_Refresh = new QToolButton(this);
  m_Refresh->setText(tr("Compare"));
  m_Refresh->setIcon(Icons::arrow_refresh());
  m_Refresh->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_Export = new QToolButton(this);
  m_Export->setText(tr("Export CSV"));
  m_Export->setIcon(Icons::save());
  m_Export->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_ExportSnapshot = new QToolButton(this);
  m_ExportSnapshot->setText(tr("Export Snapshot"));
  m_ExportSnapshot->setIcon(Icons::save());
  m_ExportSnapshot->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_ImportSnapshot = new QToolButton(this);
  m_ImportSnapshot->setText(tr("Import Snapshot as A"));
  m_ImportSnapshot->setIcon(Icons::folder_page_white());
  m_ImportSnapshot->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_ClearImported = new QPushButton(tr("Clear Imported A"), this);
  m_ClearImported->setVisible(false);

  toolbar->addWidget(new QLabel(tr("Event A"), this));
  toolbar->addWidget(m_EventA);
  toolbar->addWidget(m_SetA);
  toolbar->addWidget(new QLabel(tr("Event B"), this));
  toolbar->addWidget(m_EventB);
  toolbar->addWidget(m_SetB);
  toolbar->addWidget(m_Refresh);
  toolbar->addWidget(m_Export);
  toolbar->addWidget(m_ExportSnapshot);
  toolbar->addWidget(m_ImportSnapshot);
  toolbar->addWidget(m_ClearImported);
  toolbar->addStretch(1);

  m_Tree = new QTreeWidget(this);
  m_Tree->setColumnCount(5);
  m_Tree->setHeaderLabels({tr("Category"), tr("Name"), tr("A"), tr("B"), tr("Changed")});
  m_Tree->setAlternatingRowColors(true);
  m_Tree->setRootIsDecorated(false);
  m_Tree->setSortingEnabled(true);

  root->addLayout(toolbar);
  root->addWidget(m_Tree, 1);

  QObject::connect(m_SetA, &QToolButton::clicked, this, &TAPassDrawDiff::CaptureA);
  QObject::connect(m_SetB, &QToolButton::clicked, this, &TAPassDrawDiff::CaptureB);
  QObject::connect(m_Refresh, &QToolButton::clicked, this, &TAPassDrawDiff::Refresh);
  QObject::connect(m_Export, &QToolButton::clicked, this, &TAPassDrawDiff::ExportCSV);
  QObject::connect(m_ExportSnapshot, &QToolButton::clicked, this, &TAPassDrawDiff::ExportSnapshot);
  QObject::connect(m_ImportSnapshot, &QToolButton::clicked, this, &TAPassDrawDiff::ImportSnapshot);
  QObject::connect(m_ClearImported, &QPushButton::clicked, [this]() {
    m_ImportedRows.clear();
    m_ClearImported->setVisible(false);
    Refresh();
  });

  m_Ctx.AddCaptureViewer(this);
}

TAPassDrawDiff::~TAPassDrawDiff()
{
  m_Ctx.RemoveCaptureViewer(this);
}

void TAPassDrawDiff::OnCaptureLoaded()
{
  uint32_t lastEvent = m_Ctx.GetLastAction() ? m_Ctx.GetLastAction()->eventId : 0;
  m_EventA->setMaximum((int)lastEvent);
  m_EventB->setMaximum((int)lastEvent);
  m_EventA->setValue((int)m_Ctx.CurEvent());
  m_EventB->setValue((int)m_Ctx.CurEvent());
  Refresh();
}

void TAPassDrawDiff::OnCaptureClosed()
{
  m_Tree->clear();
  m_ImportedRows.clear();
  if(m_ClearImported)
    m_ClearImported->setVisible(false);
}

void TAPassDrawDiff::OnEventChanged(uint32_t)
{
}

void TAPassDrawDiff::CaptureA()
{
  m_EventA->setValue((int)m_Ctx.CurEvent());
  Refresh();
}

void TAPassDrawDiff::CaptureB()
{
  m_EventB->setValue((int)m_Ctx.CurEvent());
  Refresh();
}

void TAPassDrawDiff::AddRow(rdcarray<DiffRow> &rows, const QString &category, const QString &name,
                            const QString &a, const QString &b) const
{
  DiffRow row;
  row.category = category;
  row.name = name;
  row.a = a;
  row.b = b;
  row.different = a != b;
  rows.push_back(row);
}

void TAPassDrawDiff::GatherRowsForCurrentEvent(IReplayController *r, uint32_t eventId, rdcarray<DiffRow> &rows)
{
  const PipeState &pipe = m_Ctx.CurPipelineState();
  const ActionDescription *action = m_Ctx.GetAction(eventId);

  AddRow(rows, tr("Action"), tr("Name"), QString(), action ? action->GetName(m_Ctx.GetStructuredFile()) : QString());
  AddRow(rows, tr("Action"), tr("Flags"), QString(), action ? QFormatStr("0x%1").arg((uint32_t)action->flags, 0, 16) : QString());
  AddRow(rows, tr("Input Assembler"), tr("Topology"), QString(), QString::number((uint32_t)pipe.GetPrimitiveTopology()));
  AddRow(rows, tr("Input Assembler"), tr("Index Buffer"), QString(), BufferLabel(m_Ctx, pipe.GetIBuffer()));

  rdcarray<BoundVBuffer> vbs = pipe.GetVBuffers();
  for(int i = 0; i < vbs.count(); i++)
    AddRow(rows, tr("Vertex Buffers"), QFormatStr("VB %1").arg(i), QString(), BufferLabel(m_Ctx, vbs[i]));

  rdcarray<VertexInputAttribute> attrs = pipe.GetVertexInputs();
  for(int i = 0; i < attrs.count(); i++)
  {
    const VertexInputAttribute &attr = attrs[i];
    QString value = QFormatStr("vb=%1 offs=%2 inst=%3 rate=%4 fmt=%5 used=%6")
                        .arg(attr.vertexBuffer)
                        .arg(attr.byteOffset)
                        .arg(attr.perInstance)
                        .arg(attr.instanceRate)
                        .arg(attr.format.Name())
                        .arg(attr.used);
    AddRow(rows, tr("Vertex Attributes"), attr.name, QString(), value);
  }

  for(ShaderStage stage : DiffStages)
  {
    ResourceId shader = pipe.GetShader(stage);
    if(shader != ResourceId())
      AddRow(rows, tr("Shaders"), DiffStageName(m_Ctx, stage), QString(), ResourceLabel(m_Ctx, shader));

    rdcarray<UsedDescriptor> cbuffers = pipe.GetConstantBlocks(stage, true);
    for(const UsedDescriptor &descriptor : cbuffers)
    {
      AddRow(rows, tr("CBuffers"), QFormatStr("%1[%2]").arg(DiffStageName(m_Ctx, stage)).arg(descriptor.access.index),
             QString(), DescriptorLabel(m_Ctx, descriptor));

      rdcarray<ShaderVariable> vars = r->GetCBufferVariableContents(
          stage == ShaderStage::Compute ? pipe.GetComputePipelineObject() : pipe.GetGraphicsPipelineObject(),
          pipe.GetShader(stage), stage, pipe.GetShaderEntryPoint(stage), descriptor.access.index,
          descriptor.descriptor.resource, descriptor.descriptor.byteOffset, descriptor.descriptor.byteSize);
      AddCBufferVariableRows(rows, DiffStageName(m_Ctx, stage), descriptor.access.index, vars, rdcstr());
    }

    rdcarray<UsedDescriptor> ro = pipe.GetReadOnlyResources(stage, true);
    for(const UsedDescriptor &descriptor : ro)
      AddRow(rows, tr("Read-only Resources"),
             QFormatStr("%1[%2]").arg(DiffStageName(m_Ctx, stage)).arg(descriptor.access.index),
             QString(), DescriptorLabel(m_Ctx, descriptor));

    rdcarray<UsedDescriptor> rw = pipe.GetReadWriteResources(stage, true);
    for(const UsedDescriptor &descriptor : rw)
      AddRow(rows, tr("Read-write Resources"),
             QFormatStr("%1[%2]").arg(DiffStageName(m_Ctx, stage)).arg(descriptor.access.index),
             QString(), DescriptorLabel(m_Ctx, descriptor));
  }
}

void TAPassDrawDiff::Refresh()
{
  if(!m_Ctx.IsCaptureLoaded())
  {
    m_Tree->clear();
    return;
  }

  uint32_t eventA = (uint32_t)m_EventA->value();
  uint32_t eventB = (uint32_t)m_EventB->value();

  QPointer<TAPassDrawDiff> me(this);
  m_Ctx.Replay().AsyncInvoke([this, me, eventA, eventB](IReplayController *r) {
    if(!me)
      return;

    rdcarray<DiffRow> rowsA = m_ImportedRows, rowsB;
    if(rowsA.empty())
    {
      r->SetFrameEvent(eventA, false);
      GatherRowsForCurrentEvent(r, eventA, rowsA);
    }
    r->SetFrameEvent(eventB, false);
    GatherRowsForCurrentEvent(r, eventB, rowsB);

    QMap<QString, DiffRow> byKey;
    for(const DiffRow &row : rowsA)
    {
      QString key = row.category + lit("/") + row.name;
      DiffRow combined = row;
      combined.a = row.b;
      combined.b.clear();
      byKey[key] = combined;
    }

    for(const DiffRow &row : rowsB)
    {
      QString key = row.category + lit("/") + row.name;
      DiffRow &combined = byKey[key];
      combined.category = row.category;
      combined.name = row.name;
      combined.b = row.b;
    }

    rdcarray<DiffRow> combinedRows;
    for(const DiffRow &row : byKey)
    {
      DiffRow out = row;
      out.different = out.a != out.b;
      combinedRows.push_back(out);
    }

    GUIInvoke::call(this, [this, combinedRows]() { ApplyRows(combinedRows); });
  });
}

void TAPassDrawDiff::ApplyRows(const rdcarray<DiffRow> &rows)
{
  m_Tree->setSortingEnabled(false);
  m_Tree->clear();

  for(const DiffRow &row : rows)
  {
    QTreeWidgetItem *item = new QTreeWidgetItem({row.category, row.name, row.a, row.b,
                                                row.different ? tr("Yes") : QString()});
    if(row.different)
      item->setBackgroundColor(4, QColor(255, 220, 160));
    m_Tree->addTopLevelItem(item);
  }

  for(int col = 0; col < m_Tree->columnCount(); col++)
    m_Tree->resizeColumnToContents(col);

  m_Tree->setSortingEnabled(true);
}

void TAPassDrawDiff::ExportCSV()
{
  QString filename = RDDialog::getSaveFileName(this, tr("Export Pass/Draw Diff CSV"), QString(),
                                               tr("CSV files (*.csv)"));
  if(filename.isEmpty())
    return;

  QFile file(filename);
  if(!file.open(QIODevice::WriteOnly | QIODevice::Text))
    return;

  QTextStream ts(&file);
  for(int col = 0; col < m_Tree->columnCount(); col++)
  {
    if(col)
      ts << lit(",");
    ts << lit("\"") << m_Tree->headerItem()->text(col).replace(lit("\""), lit("\"\"")) << lit("\"");
  }
  ts << lit("\n");

  for(int row = 0; row < m_Tree->topLevelItemCount(); row++)
  {
    QTreeWidgetItem *item = m_Tree->topLevelItem(row);
    for(int col = 0; col < m_Tree->columnCount(); col++)
    {
      if(col)
        ts << lit(",");
      QString text = item->text(col);
      ts << lit("\"") << text.replace(lit("\""), lit("\"\"")) << lit("\"");
    }
    ts << lit("\n");
  }
}

void TAPassDrawDiff::ExportSnapshot()
{
  if(!m_Ctx.IsCaptureLoaded())
    return;

  QString filename = RDDialog::getSaveFileName(this, tr("Export Pass/Draw Snapshot"), QString(),
                                               tr("TA diff snapshot (*.tadiff);;CSV files (*.csv)"));
  if(filename.isEmpty())
    return;

  rdcarray<DiffRow> rows;
  uint32_t eventId = (uint32_t)m_EventB->value();
  m_Ctx.Replay().BlockInvoke([&](IReplayController *r) {
    r->SetFrameEvent(eventId, false);
    GatherRowsForCurrentEvent(r, eventId, rows);
  });

  QFile file(filename);
  if(!file.open(QIODevice::WriteOnly | QIODevice::Text))
    return;

  QTextStream ts(&file);
  ts << lit("Category,Name,Value\n");
  for(const DiffRow &row : rows)
  {
    QStringList cols = {row.category, row.name, row.b};
    for(int i = 0; i < cols.count(); i++)
    {
      if(i)
        ts << lit(",");
      ts << lit("\"") << cols[i].replace(lit("\""), lit("\"\"")) << lit("\"");
    }
    ts << lit("\n");
  }
}

void TAPassDrawDiff::ImportSnapshot()
{
  QString filename = RDDialog::getOpenFileName(this, tr("Import Pass/Draw Snapshot"), QString(),
                                               tr("TA diff snapshot (*.tadiff *.csv);;CSV files (*.csv)"));
  if(filename.isEmpty())
    return;

  QFile file(filename);
  if(!file.open(QIODevice::ReadOnly | QIODevice::Text))
    return;

  m_ImportedRows.clear();
  QTextStream ts(&file);
  bool first = true;
  while(!ts.atEnd())
  {
    QString line = ts.readLine();
    if(first)
    {
      first = false;
      if(line.startsWith(lit("Category,")))
        continue;
    }

    QStringList cols;
    QString cur;
    bool quote = false;
    for(int i = 0; i < line.size(); i++)
    {
      QChar c = line[i];
      if(c == QLatin1Char('"'))
      {
        if(quote && i + 1 < line.size() && line[i + 1] == QLatin1Char('"'))
        {
          cur += c;
          i++;
        }
        else
        {
          quote = !quote;
        }
      }
      else if(c == QLatin1Char(',') && !quote)
      {
        cols << cur;
        cur.clear();
      }
      else
      {
        cur += c;
      }
    }
    cols << cur;

    if(cols.count() < 3)
      continue;

    DiffRow row;
    row.category = cols[0];
    row.name = cols[1];
    row.b = cols[2];
    m_ImportedRows.push_back(row);
  }

  m_ClearImported->setVisible(!m_ImportedRows.empty());
  Refresh();
}
