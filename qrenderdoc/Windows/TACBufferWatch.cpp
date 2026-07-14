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

#include "TACBufferWatch.h"
#include <QApplication>
#include <QCheckBox>
#include <QComboBox>
#include <QFile>
#include <QFileDialog>
#include <QHBoxLayout>
#include <QHeaderView>
#include <QLabel>
#include <QPainter>
#include <QRegExp>
#include <QSplitter>
#include <QSpinBox>
#include <QTextStream>
#include <functional>
#include <QToolButton>
#include <QVBoxLayout>
#include <QPointer>
#include "Code/QRDUtils.h"
#include "Code/Resources.h"

static const ShaderStage WatchStages[] = {
    ShaderStage::Vertex, ShaderStage::Hull, ShaderStage::Domain, ShaderStage::Geometry,
    ShaderStage::Pixel,  ShaderStage::Compute, ShaderStage::Amplification, ShaderStage::Mesh,
};

static QString StageName(ICaptureContext &ctx, ShaderStage stage)
{
  return ToQStr(stage, ctx.APIProps().pipelineType);
}

static QString WatchLabel(ICaptureContext &ctx, const TACBufferWatch::WatchVariable &watch)
{
  return QFormatStr("%1 cbuffer[%2].%3")
      .arg(StageName(ctx, watch.stage))
      .arg(watch.slot)
      .arg(QString(watch.path));
}

static QString ValueString(const ShaderVariable &var)
{
  if(!var.members.empty())
    return QApplication::translate("TACBufferWatch", "<struct/array>");

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


class TACBufferWatchGraph : public QWidget
{
public:
  explicit TACBufferWatchGraph(QWidget *parent = NULL) : QWidget(parent)
  {
    setMinimumHeight(140);
  }

  void setSamples(const rdcarray<TACBufferWatch::WatchSample> &samples, bool changesOnly)
  {
    m_Series.clear();

    QMap<QString, QVector<QPointF>> points;
    for(const TACBufferWatch::WatchSample &sample : samples)
    {
      if(changesOnly && !sample.changed)
        continue;

      QRegExp number(lit("[-+]?(?:\\d*\\.\\d+|\\d+)(?:[eE][-+]?\\d+)?"));
      if(number.indexIn(QString(sample.value)) < 0)
        continue;

      bool ok = false;
      double value = number.cap(0).toDouble(&ok);
      if(!ok)
        continue;

      QString key = QFormatStr("%1[%2].%3")
                        .arg((uint32_t)sample.stage)
                        .arg(sample.slot)
                        .arg(QString(sample.path));
      points[key].push_back(QPointF(sample.eventId, value));
    }

    int idx = 0;
    for(auto it = points.begin(); it != points.end(); ++it)
    {
      Series series;
      series.name = it.key();
      series.points = it.value();
      series.color = QColor::fromHsv((idx * 47) % 360, 180, 220);
      m_Series.push_back(series);
      idx++;
    }

    update();
  }

protected:
  void paintEvent(QPaintEvent *) override
  {
    QPainter painter(this);
    painter.fillRect(rect(), palette().base());
    painter.setRenderHint(QPainter::Antialiasing, true);

    QRect plot = rect().adjusted(42, 12, -12, -28);
    painter.setPen(palette().mid().color());
    painter.drawRect(plot);

    if(m_Series.empty())
    {
      painter.setPen(palette().text().color());
      painter.drawText(plot, Qt::AlignCenter, tr("No numeric watched values to plot"));
      return;
    }

    double minX = DBL_MAX, maxX = -DBL_MAX, minY = DBL_MAX, maxY = -DBL_MAX;
    for(const Series &series : m_Series)
    {
      for(const QPointF &point : series.points)
      {
        minX = qMin(minX, point.x());
        maxX = qMax(maxX, point.x());
        minY = qMin(minY, point.y());
        maxY = qMax(maxY, point.y());
      }
    }

    if(minX == maxX)
      maxX = minX + 1.0;
    if(minY == maxY)
      maxY = minY + 1.0;

    auto mapPoint = [&](const QPointF &point) {
      double x = (point.x() - minX) / (maxX - minX);
      double y = (point.y() - minY) / (maxY - minY);
      return QPointF(plot.left() + x * plot.width(), plot.bottom() - y * plot.height());
    };

    for(const Series &series : m_Series)
    {
      painter.setPen(QPen(series.color, 2.0f));
      QPointF prev;
      bool hasPrev = false;
      for(const QPointF &point : series.points)
      {
        QPointF mapped = mapPoint(point);
        if(hasPrev)
          painter.drawLine(prev, mapped);
        painter.drawEllipse(mapped, 2.5, 2.5);
        prev = mapped;
        hasPrev = true;
      }
    }

    painter.setPen(palette().text().color());
    painter.drawText(QRect(0, plot.top(), 40, 20), Qt::AlignRight | Qt::AlignVCenter,
                     Formatter::Format(minY));
    painter.drawText(QRect(0, plot.bottom() - 20, 40, 20), Qt::AlignRight | Qt::AlignVCenter,
                     Formatter::Format(maxY));
    painter.drawText(QRect(plot.left(), plot.bottom() + 4, 80, 20), Qt::AlignLeft | Qt::AlignVCenter,
                     QString::number((uint32_t)minX));
    painter.drawText(QRect(plot.right() - 80, plot.bottom() + 4, 80, 20),
                     Qt::AlignRight | Qt::AlignVCenter, QString::number((uint32_t)maxX));
  }

private:
  struct Series
  {
    QString name;
    QVector<QPointF> points;
    QColor color;
  };

  QVector<Series> m_Series;
};

static const ShaderVariable *FindVariable(const rdcarray<ShaderVariable> &vars, const rdcstr &path)
{
  int dot = path.find('.');
  rdcstr head = dot >= 0 ? path.substr(0, dot) : path;
  rdcstr tail = dot >= 0 ? path.substr(dot + 1) : rdcstr();

  for(const ShaderVariable &var : vars)
  {
    if(var.name == head)
      return tail.empty() ? &var : FindVariable(var.members, tail);
  }

  return NULL;
}

TACBufferWatch::TACBufferWatch(ICaptureContext &ctx, QWidget *parent) : QFrame(parent), m_Ctx(ctx)
{
  setWindowTitle(tr("TA CBuffer Watch"));

  QVBoxLayout *root = new QVBoxLayout(this);
  root->setContentsMargins(3, 3, 3, 3);

  QHBoxLayout *toolbar = new QHBoxLayout();
  toolbar->setContentsMargins(0, 0, 0, 0);

  m_AddCurrent = new QToolButton(this);
  m_AddCurrent->setText(tr("Add Current CBuffers"));
  m_AddCurrent->setIcon(Icons::add());
  m_AddCurrent->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_WatchList = new QComboBox(this);
  m_WatchList->setMinimumWidth(260);

  m_MaxEvents = new QSpinBox(this);
  m_MaxEvents->setRange(1, 5000);
  m_MaxEvents->setValue(300);
  m_MaxEvents->setToolTip(tr("Maximum draw/dispatch events to scan from the current event backwards"));

  m_ChangesOnly = new QCheckBox(tr("Only changes"), this);

  m_Refresh = new QToolButton(this);
  m_Refresh->setText(tr("Refresh"));
  m_Refresh->setIcon(Icons::arrow_refresh());
  m_Refresh->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_Clear = new QToolButton(this);
  m_Clear->setText(tr("Clear"));
  m_Clear->setIcon(Icons::cross());
  m_Clear->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  m_Export = new QToolButton(this);
  m_Export->setText(tr("Export CSV"));
  m_Export->setIcon(Icons::save());
  m_Export->setToolButtonStyle(Qt::ToolButtonTextBesideIcon);

  toolbar->addWidget(m_AddCurrent);
  toolbar->addWidget(new QLabel(tr("Watch"), this));
  toolbar->addWidget(m_WatchList, 1);
  toolbar->addWidget(new QLabel(tr("Events"), this));
  toolbar->addWidget(m_MaxEvents);
  toolbar->addWidget(m_ChangesOnly);
  toolbar->addWidget(m_Refresh);
  toolbar->addWidget(m_Clear);
  toolbar->addWidget(m_Export);

  m_Graph = new TACBufferWatchGraph(this);

  m_Table = new QTableWidget(this);
  m_Table->setColumnCount(7);
  m_Table->setHorizontalHeaderLabels(
      {tr("EID"), tr("Action"), tr("Stage"), tr("Slot"), tr("Variable"), tr("Value"), tr("Changed")});
  m_Table->horizontalHeader()->setStretchLastSection(true);
  m_Table->setEditTriggers(QAbstractItemView::NoEditTriggers);
  m_Table->setSelectionBehavior(QAbstractItemView::SelectRows);
  m_Table->setSortingEnabled(true);

  QSplitter *splitter = new QSplitter(Qt::Vertical, this);
  splitter->addWidget(m_Graph);
  splitter->addWidget(m_Table);
  splitter->setStretchFactor(0, 1);
  splitter->setStretchFactor(1, 3);

  root->addLayout(toolbar);
  root->addWidget(splitter, 1);

  QObject::connect(m_AddCurrent, &QToolButton::clicked, this, &TACBufferWatch::AddCurrentCBufferVariables);
  QObject::connect(m_Refresh, &QToolButton::clicked, this, &TACBufferWatch::Refresh);
  QObject::connect(m_Clear, &QToolButton::clicked, [this]() {
    m_Watches.clear();
    PopulateWatchMenu();
    m_Table->setRowCount(0);
    m_Graph->setSamples({}, false);
  });
  QObject::connect(m_Export, &QToolButton::clicked, this, &TACBufferWatch::ExportCSV);
  QObject::connect(m_ChangesOnly, &QCheckBox::toggled, this, &TACBufferWatch::Refresh);
  QObject::connect(m_WatchList, OverloadedSlot<int>::of(&QComboBox::currentIndexChanged),
                   [this](int) { Refresh(); });

  PopulateWatchMenu();
  m_Ctx.AddCaptureViewer(this);
}

TACBufferWatch::~TACBufferWatch()
{
  m_Ctx.RemoveCaptureViewer(this);
}

void TACBufferWatch::OnCaptureLoaded()
{
  PopulateWatchMenu();
  Refresh();
}

void TACBufferWatch::OnCaptureClosed()
{
  m_Table->setRowCount(0);
  if(m_Graph)
    m_Graph->setSamples({}, false);
}

void TACBufferWatch::OnEventChanged(uint32_t)
{
  Refresh();
}

void TACBufferWatch::GatherVariables(const rdcarray<ShaderVariable> &vars, const rdcstr &prefix,
                                     rdcarray<WatchVariable> &out) const
{
  for(const ShaderVariable &var : vars)
  {
    rdcstr path = prefix.empty() ? var.name : prefix + "." + var.name;

    if(var.members.empty())
    {
      WatchVariable watch;
      watch.path = path;
      out.push_back(watch);
    }
    else
    {
      GatherVariables(var.members, path, out);
    }
  }
}

void TACBufferWatch::AddCurrentCBufferVariables()
{
  if(!m_Ctx.IsCaptureLoaded())
    return;

  const PipeState &pipe = m_Ctx.CurPipelineState();
  int added = 0;

  for(ShaderStage stage : WatchStages)
  {
    const ShaderReflection *reflection = pipe.GetShaderReflection(stage);
    if(!reflection)
      continue;

    for(int slot = 0; slot < reflection->constantBlocks.count(); slot++)
    {
      UsedDescriptor descriptor = pipe.GetConstantBlock(stage, slot, 0);
      rdcarray<ShaderVariable> vars;
      m_Ctx.Replay().BlockInvoke([&](IReplayController *r) {
        vars = r->GetCBufferVariableContents(
            stage == ShaderStage::Compute ? pipe.GetComputePipelineObject() : pipe.GetGraphicsPipelineObject(),
            pipe.GetShader(stage), stage, pipe.GetShaderEntryPoint(stage), (uint32_t)slot,
            descriptor.descriptor.resource, descriptor.descriptor.byteOffset,
            descriptor.descriptor.byteSize);
      });

      rdcarray<WatchVariable> gathered;
      GatherVariables(vars, rdcstr(), gathered);

      for(WatchVariable &watch : gathered)
      {
        watch.stage = stage;
        watch.slot = (uint32_t)slot;

        bool exists = false;
        for(const WatchVariable &existing : m_Watches)
          exists |= existing.stage == watch.stage && existing.slot == watch.slot && existing.path == watch.path;

        if(!exists)
        {
          m_Watches.push_back(watch);
          added++;
        }
      }
    }
  }

  PopulateWatchMenu();
  Refresh();
}

void TACBufferWatch::PopulateWatchMenu()
{
  m_WatchList->blockSignals(true);
  m_WatchList->clear();
  m_WatchList->addItem(tr("All watched variables"), -1);

  for(int i = 0; i < m_Watches.count(); i++)
    m_WatchList->addItem(WatchLabel(m_Ctx, m_Watches[i]), i);

  m_WatchList->setEnabled(!m_Watches.empty());
  m_WatchList->blockSignals(false);
}

void TACBufferWatch::GatherSamplesForEvent(IReplayController *r, uint32_t eventId,
                                           const ActionDescription *action,
                                           rdcarray<WatchSample> &out) const
{
  r->SetFrameEvent(eventId, false);
  const PipeState &pipe = m_Ctx.CurPipelineState();
  int selected = m_WatchList->currentData().toInt();

  for(int i = 0; i < m_Watches.count(); i++)
  {
    if(selected >= 0 && selected != i)
      continue;

    const WatchVariable &watch = m_Watches[i];
    const ShaderReflection *reflection = pipe.GetShaderReflection(watch.stage);
    if(!reflection || watch.slot >= (uint32_t)reflection->constantBlocks.count())
      continue;

    UsedDescriptor descriptor = pipe.GetConstantBlock(watch.stage, watch.slot, 0);
    rdcarray<ShaderVariable> vars = r->GetCBufferVariableContents(
        watch.stage == ShaderStage::Compute ? pipe.GetComputePipelineObject() : pipe.GetGraphicsPipelineObject(),
        pipe.GetShader(watch.stage), watch.stage, pipe.GetShaderEntryPoint(watch.stage), watch.slot,
        descriptor.descriptor.resource, descriptor.descriptor.byteOffset, descriptor.descriptor.byteSize);

    const ShaderVariable *var = FindVariable(vars, watch.path);
    if(!var)
      continue;

    WatchSample sample;
    sample.eventId = eventId;
    sample.actionName = action ? action->GetName(m_Ctx.GetStructuredFile()) : rdcstr();
    sample.stage = watch.stage;
    sample.slot = watch.slot;
    sample.path = watch.path;
    sample.value = ValueString(*var);
    out.push_back(sample);
  }
}

void TACBufferWatch::Refresh()
{
  if(!m_Ctx.IsCaptureLoaded() || m_Watches.empty())
  {
    m_Table->setRowCount(0);
    if(m_Graph)
      m_Graph->setSamples({}, false);
    return;
  }

  rdcarray<uint32_t> events;
  uint32_t curEvent = m_Ctx.CurEvent();
  for(const ActionDescription &action : m_Ctx.CurRootActions())
  {
    std::function<void(const ActionDescription &)> gather = [&](const ActionDescription &a) {
      if(a.eventId <= curEvent &&
         (a.flags & (ActionFlags::Drawcall | ActionFlags::Dispatch | ActionFlags::MeshDispatch)))
        events.push_back(a.eventId);
      for(const ActionDescription &child : a.children)
        gather(child);
    };
    gather(action);
  }

  std::sort(events.begin(), events.end());
  while(events.count() > m_MaxEvents->value())
    events.erase(0);

  QPointer<TACBufferWatch> me(this);
  m_Ctx.Replay().AsyncInvoke([this, me, events](IReplayController *r) {
    if(!me)
      return;

    rdcarray<WatchSample> samples;
    for(uint32_t eventId : events)
      GatherSamplesForEvent(r, eventId, m_Ctx.GetAction(eventId), samples);

    rdcstr key;
    QMap<QString, QString> previous;
    for(WatchSample &sample : samples)
    {
      QString sampleKey = QFormatStr("%1:%2:%3")
                              .arg((uint32_t)sample.stage)
                              .arg(sample.slot)
                              .arg(QString(sample.path));
      QString value = QString(sample.value);
      sample.changed = previous.contains(sampleKey) && previous[sampleKey] != value;
      previous[sampleKey] = value;
    }

    GUIInvoke::call(this, [this, samples]() { ApplySamples(samples); });
  });
}

void TACBufferWatch::ApplySamples(const rdcarray<WatchSample> &samples)
{
  if(m_Graph)
    m_Graph->setSamples(samples, m_ChangesOnly->isChecked());

  m_Table->setSortingEnabled(false);
  m_Table->setRowCount(0);

  for(const WatchSample &sample : samples)
  {
    if(m_ChangesOnly->isChecked() && !sample.changed)
      continue;

    int row = m_Table->rowCount();
    m_Table->insertRow(row);
    QStringList cols = {
        QString::number(sample.eventId), QString(sample.actionName), StageName(m_Ctx, sample.stage),
        QString::number(sample.slot), QString(sample.path), QString(sample.value),
        sample.changed ? tr("Yes") : QString(),
    };

    for(int col = 0; col < cols.count(); col++)
      m_Table->setItem(row, col, new QTableWidgetItem(cols[col]));
  }

  m_Table->resizeColumnsToContents();
  m_Table->setSortingEnabled(true);
}

void TACBufferWatch::ExportCSV()
{
  QString filename = RDDialog::getSaveFileName(this, tr("Export CBuffer Watch CSV"), QString(),
                                               tr("CSV files (*.csv)"));
  if(filename.isEmpty())
    return;

  QFile file(filename);
  if(!file.open(QIODevice::WriteOnly | QIODevice::Text))
    return;

  QTextStream ts(&file);
  for(int col = 0; col < m_Table->columnCount(); col++)
  {
    if(col)
      ts << lit(",");
    ts << lit("\"") << m_Table->horizontalHeaderItem(col)->text().replace(lit("\""), lit("\"\"")) << lit("\"");
  }
  ts << lit("\n");

  for(int row = 0; row < m_Table->rowCount(); row++)
  {
    for(int col = 0; col < m_Table->columnCount(); col++)
    {
      if(col)
        ts << lit(",");
      QString text = m_Table->item(row, col) ? m_Table->item(row, col)->text() : QString();
      ts << lit("\"") << text.replace(lit("\""), lit("\"\"")) << lit("\"");
    }
    ts << lit("\n");
  }
}